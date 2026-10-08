"""Regression coverage for authentication and credential persistence bugs."""
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database, security
from app.routes import auth, agent_lab, workspace
from quant_platform.agents_bridge.llm_settings import LLMSettingsStore


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'app.db'))
    for key in ['FELLOWQUANT_ADMIN_EMAIL', 'FELLOWQUANT_ADMIN_PASSWORD', 'SMTP_HOST', 'SMTP_FROM']:
        monkeypatch.delenv(key, raising=False)
    database.init_db()
    auth._RESET_CODES.clear()
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


def account(api):
    data = {'name': 'test-user', 'email': 'test@example.test', 'password': 'initial-password'}
    result = api.post('/api/v1/auth/register', json=data)
    assert result.status_code == 201
    return result.json()


def test_fresh_database_has_no_public_admin(api):
    with database.get_conn() as conn:
        assert conn.execute('SELECT COUNT(*) FROM users WHERE is_admin=1').fetchone()[0] == 0
    user = account(api)
    assert not user['is_admin']


def test_forgot_password_without_mail_service_is_disabled(api):
    account(api)
    result = api.post('/api/v1/auth/forgot/request', json={'name': 'test-user', 'email': 'test@example.test'})
    assert result.status_code == 503 and 'code' not in result.json()
    assert not auth._RESET_CODES


def test_reset_code_is_only_sent_to_mailbox(api, monkeypatch):
    user = account(api)
    old_token = api.post('/api/v1/auth/login', json={'email': 'test@example.test', 'password': 'initial-password'}).json()['token']
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_FROM', 'noreply@example.test')
    with patch.object(auth.smtplib, 'SMTP') as smtp:
        response = api.post('/api/v1/auth/forgot/request', json={'name': 'test-user', 'email': 'test@example.test'})
        assert response.status_code == 200 and 'code' not in response.json()
        code = auth._RESET_CODES[user['id']][0]
        assert code not in response.text
        server = smtp.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        mail = server.send_message.call_args.args[0]
        assert mail['To'] == 'test@example.test' and code in mail.get_content()
        assert api.post('/api/v1/auth/forgot/request', json={'name': 'test-user', 'email': 'test@example.test'}).status_code == 429
    result = api.post('/api/v1/auth/forgot/reset', json={'name': 'test-user', 'email': 'test@example.test', 'code': code, 'new_password': 'changed-password'})
    assert result.status_code == 200 and user['id'] not in auth._RESET_CODES
    assert api.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + old_token}).status_code == 401
    assert api.post('/api/v1/auth/login', json={'email': 'test@example.test', 'password': 'initial-password'}).status_code == 401
    assert api.post('/api/v1/auth/login', json={'email': 'test@example.test', 'password': 'changed-password'}).status_code == 200


def test_mail_failure_does_not_issue_code(api, monkeypatch):
    account(api)
    monkeypatch.setenv('SMTP_HOST', 'smtp.example.test')
    monkeypatch.setenv('SMTP_FROM', 'noreply@example.test')
    with patch.object(auth.smtplib, 'SMTP', side_effect=OSError('secret details')):
        result = api.post('/api/v1/auth/forgot/request', json={'name': 'test-user', 'email': 'test@example.test'})
    assert result.status_code == 503 and 'secret details' not in result.text
    assert not auth._RESET_CODES


def test_local_secret_is_random_persistent_and_env_overridable(tmp_path, monkeypatch):
    monkeypatch.delenv('APP_SECRET', raising=False)
    monkeypatch.setenv('FELLOWQUANT_DATA_DIR', str(tmp_path))
    one = security._load_secret()
    assert len(one) == 64 and security._load_secret() == one
    monkeypatch.setenv('FELLOWQUANT_DATA_DIR', str(tmp_path / 'other'))
    assert security._load_secret() != one
    monkeypatch.setenv('APP_SECRET', 'configured-secret')
    assert security._load_secret() == 'configured-secret'


def test_llm_settings_update_without_reentering_key(tmp_path, monkeypatch):
    store = LLMSettingsStore(tmp_path / 'llm.json')
    monkeypatch.setattr(agent_lab, '_llm_store', lambda _: store)
    store.save('custom', base_url='http://old/v1', api_key='existing-key', model='old')
    agent_lab.agent_config_save(agent_lab.ProviderSaveIn(provider='custom', base_url='http://new/v1', model='new'), {'id': 1})
    assert store.get('custom') == {'base_url': 'http://new/v1', 'api_key': 'existing-key', 'model': 'new'}
    agent_lab.agent_config_save(agent_lab.ProviderSaveIn(provider='ollama', base_url='http://localhost:11434/v1', model='qwen2.5:7b'), {'id': 1})
    assert store.get('ollama')['model'] == 'qwen2.5:7b'


def test_decision_provider_is_not_offered_as_chat_model(tmp_path, monkeypatch):
    store = LLMSettingsStore(tmp_path / 'llm.json')
    monkeypatch.setattr(workspace, '_llm_store', lambda _: store)
    assert 'openrouter' not in [p['key'] for p in workspace.nl_providers({'id': 1})['providers']]
    with pytest.raises(Exception) as exc:
        workspace.nl_generate(workspace.NlGenerateIn(description='动量策略', provider='openrouter'), {'id': 1})
    assert exc.value.status_code == 422


def test_nl_generation_honors_page_configuration(tmp_path, monkeypatch):
    store = LLMSettingsStore(tmp_path / 'llm.json')
    monkeypatch.setattr(workspace, '_llm_store', lambda _: store)
    definition = MagicMock()
    definition.minimum_history_days = 20
    monkeypatch.setattr(workspace, 'definition_to_frontend', lambda _: {})
    monkeypatch.setattr(workspace, 'definition_explanation', lambda *a, **kw: 'generated')
    with patch.object(workspace, 'create_llm_client') as create, \
         patch.object(workspace, 'NLStrategyBuilder') as builder:
        builder.return_value.generate.return_value = definition
        result = workspace.nl_generate(workspace.NlGenerateIn(description='动量策略', provider='custom',
                                        base_url='http://localhost:1234/v1', api_key='request-only-key', model='custom-model'), {'id': 1})
    assert result['minimum_history_days'] == 20
    assert create.call_args.kwargs['api_key'] == 'request-only-key'
    assert create.call_args.kwargs['model'] == 'custom-model'
    assert create.call_args.kwargs['base_url'] == 'http://localhost:1234/v1'
    assert store.get('custom')['api_key'] == ''
