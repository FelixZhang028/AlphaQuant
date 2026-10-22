"""Regression coverage for authentication and credential persistence bugs."""
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database, security
from app.quant import mailer
from app.routes import auth, workspace


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
    with patch.object(mailer.smtplib, 'SMTP') as smtp:
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
    with patch.object(mailer.smtplib, 'SMTP', side_effect=OSError('secret details')):
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


def test_nl_generation_uses_the_platform_model_and_counts_it(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'app.db'))
    database.init_db()
    with database.get_conn() as conn:
        conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (1, 'u', 'u@example.test', 'h', 's', 'now')")
    monkeypatch.setenv('OPENROUTER_API_KEY', 'platform-key')
    monkeypatch.setenv('FELLOWQUANT_AI_DAILY_STRATEGIES', '1')
    definition = MagicMock()
    definition.minimum_history_days = 20
    monkeypatch.setattr(workspace, 'definition_to_frontend', lambda _: {})
    monkeypatch.setattr(workspace, 'definition_explanation', lambda *a, **kw: 'generated')
    user = {'id': 1, 'is_admin': False}
    with patch.object(workspace, 'NLStrategyBuilder') as builder:
        builder.return_value.generate.return_value = definition
        first = workspace.nl_generate(workspace.NlGenerateIn(description='动量策略'), user)
        client = builder.call_args.args[0]
        assert client.api_key == 'platform-key' and client.base_url == 'https://openrouter.ai/api/v1'
        assert first['model'] == 'deepseek-v4-pro' and first['note'] == ''
        # 次数用完：改用离线规则识别，并说明原因
        second = workspace.nl_generate(workspace.NlGenerateIn(description='动量策略'), user)
        assert builder.call_args.args[0].name == 'mock'
        assert second['model'] is None and '用完' in second['note']
    assert workspace.nl_status(user)['usage'] == {'limit': 1, 'used': 1, 'remaining': 0, 'cost': 2, 'points': 0}


def test_nl_generation_without_a_platform_model_is_offline(monkeypatch):
    for name in ('OPENROUTER_API_KEY', 'FELLOWQUANT_AI_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    definition = MagicMock()
    definition.minimum_history_days = 20
    monkeypatch.setattr(workspace, 'definition_to_frontend', lambda _: {})
    monkeypatch.setattr(workspace, 'definition_explanation', lambda *a, **kw: 'generated')
    with patch.object(workspace, 'NLStrategyBuilder') as builder:
        builder.return_value.generate.return_value = definition
        result = workspace.nl_generate(workspace.NlGenerateIn(description='动量策略'), {'id': 1})
    assert builder.call_args.args[0].name == 'mock' and result['model'] is None
