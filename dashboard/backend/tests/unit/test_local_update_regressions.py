"""Regressions found during the October local update; no external API calls."""
from concurrent.futures import ThreadPoolExecutor
import logging
from threading import Event
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
import requests

from app import database
from app.quant import platform_ai
from app.routes import auth, workspace
from quant_platform.jev import JevClient, NoulRequest
from quant_platform.jev.client import OPENROUTER_DECISIONS_URL, TYPESAFE_DECISIONS_URL


@pytest.fixture
def account_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, 'DB_PATH', str(tmp_path / 'app.db'))
    database.init_db()
    with database.get_conn() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) "
                         "VALUES (?, 'test', ?, 'h', 's', 'now')", (uid, f'u{uid}@example.test'))
    return {'id': 1, 'is_admin': False}


def test_native_key_selects_official_endpoint_without_openrouter(monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    assert platform_ai.decision_client() is None
    monkeypatch.setenv('TYPESAFE_API_KEY', 'native-test')
    client = platform_ai.decision_client()
    assert (client.api_key, client.base_url, client.model) == ('native-test', TYPESAFE_DECISIONS_URL, 'jev-latest')
    monkeypatch.setenv('OPENROUTER_API_KEY', 'router-test')
    assert platform_ai.decision_client().api_key == 'native-test'
    monkeypatch.delenv('TYPESAFE_API_KEY')
    client = platform_ai.decision_client()
    assert (client.api_key, client.base_url, client.model) == ('router-test', OPENROUTER_DECISIONS_URL, 'typesafe/jev-1.13')
    monkeypatch.setenv('JEV_API_KEY', 'alias-test')
    assert platform_ai.decision_client().base_url == TYPESAFE_DECISIONS_URL


def test_native_http_contract_and_redirects_do_not_forward_credentials():
    response = MagicMock(status_code=200)
    response.__enter__.return_value = response
    response.json.return_value = {'answers': {'decision': {'type': 'noul', 'noul': .8}}}
    with patch('quant_platform.jev.client.requests.post', return_value=response) as post:
        assert JevClient('native-test').noul(NoulRequest('True?', state=None)).probability == .8
        assert post.call_args.args[0] == TYPESAFE_DECISIONS_URL
        assert post.call_args.kwargs['json']['model'] == 'jev-latest'
        assert post.call_args.kwargs['json']['state'] == {}
        assert post.call_args.kwargs['allow_redirects'] is False
        response.status_code = 307
        with pytest.raises(ValueError, match='重定向'):
            JevClient('native-test').noul(NoulRequest('True?'))


@pytest.mark.parametrize('answer', [None, {}, {'type': 'noul', 'noul': None},
                                  {'type': 'noul', 'noul': float('nan')}])
def test_bad_provider_answers_are_rejected(answer):
    with patch.object(JevClient, '_post', return_value={'answers': {'decision': answer}}):
        with pytest.raises(ValueError):
            JevClient('test').noul(NoulRequest('Q'))


def test_universe_filters_insert_and_update_preserve_symbols_and_other_users(account_db):
    user = account_db
    workspace._save_universe(1, ['600000'])
    workspace._save_universe(2, ['000001'])
    first = {'exclude_st': True, 'exclude_suspended': False, 'minimum_listing_days': 80,
             'minimum_history_days': 160, 'minimum_average_amount': 10000}
    assert workspace.universe_filters(first, user) == {'saved': True}
    workspace.universe_filters({**first, 'exclude_suspended': True}, user)
    with database.get_conn() as conn:
        one = conn.execute('SELECT * FROM universe WHERE user_id=1').fetchone()
        two = conn.execute('SELECT * FROM universe WHERE user_id=2').fetchone()
    assert one['exclude_suspended'] == 1 and one['minimum_listing_days'] == 80
    assert '600000' in one['symbols'] and '000001' in two['symbols']
    assert two['minimum_listing_days'] != 80


def test_daily_quota_reserves_last_slot_before_network_and_refunds_failures(account_db, monkeypatch):
    monkeypatch.setenv('FELLOWQUANT_AI_DAILY_REVIEWS', '1')
    entered, release = Event(), Event()

    def first_call():
        with platform_ai.quota_call(account_db, 'review'):
            entered.set()
            assert release.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(first_call)
        try:
            assert entered.wait(5)
            with pytest.raises(platform_ai.QuotaExceeded):
                with platform_ai.quota_call(account_db, 'review'):
                    pytest.fail('Concurrent request exceeded quota')
        finally:
            release.set()
        future.result()
    assert platform_ai.usage(account_db, 'review')['used'] == 1
    user2 = {'id': 2}
    with pytest.raises(requests.Timeout):
        with platform_ai.quota_call(user2, 'review'):
            raise requests.Timeout()
    assert platform_ai.usage(user2, 'review')['used'] == 0
    with platform_ai.quota_call(user2, 'review'):
        pass
    assert platform_ai.usage(user2, 'review')['used'] == 1


def test_failed_call_crossing_midnight_refunds_the_original_day(account_db, monkeypatch):
    monkeypatch.setattr(platform_ai, '_today', lambda: '2026-10-17')
    with pytest.raises(ValueError):
        with platform_ai.quota_call(account_db, 'review'):
            monkeypatch.setattr(platform_ai, '_today', lambda: '2026-10-18')
            raise ValueError('failed')
    with database.get_conn() as conn:
        row = conn.execute('SELECT day, count FROM ai_usage').fetchone()
    assert (row['day'], row['count']) == ('2026-10-17', 0)


def test_invalid_credentials_never_appear_in_validation_logs(account_db, caplog):
    from app.main import validation_exception_handler
    from fastapi.exceptions import RequestValidationError
    app = FastAPI()
    app.include_router(auth.router)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    with caplog.at_level(logging.INFO, logger='uvicorn.error'):
        result = TestClient(app).post('/api/v1/auth/register', json={
            'name': 'test', 'email': 'test@example.test', 'password': 'SECRET'})
    assert result.status_code == 422 and 'SECRET' not in caplog.text
