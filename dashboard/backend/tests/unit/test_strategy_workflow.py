"""Unified research workflow: saved identity, template fidelity, effective inputs."""
import json
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from app.quant import runtime
from app.routes import backtests, workspace
from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.risk.config import RiskLimits
from quant_platform.strategies.discovery import StrategyCatalog
from quant_platform.strategies.templates import beginner_templates
from quant_platform.user_strategies.starter import STARTER_STRATEGY_CODE
from test_research_integrity import api, save_run


@pytest.fixture
def workflow(api, monkeypatch):
    client, connect, root = api
    with connect() as conn:
        conn.execute("CREATE TABLE strategy_packages (id INTEGER PRIMARY KEY, user_id INTEGER, package_id TEXT, name TEXT, definition TEXT, top_n INTEGER, rebalance TEXT, source TEXT, created_at TEXT)")
        conn.execute("CREATE TABLE user_strategies (id INTEGER PRIMARY KEY, user_id INTEGER, plugin_name TEXT, display_name TEXT, description TEXT, source TEXT, code TEXT, parameters TEXT, created_at TEXT, updated_at TEXT, UNIQUE(user_id, plugin_name))")
    captured = []
    catalog = StrategyCatalog()
    metadata = catalog.metadata()
    defaults = BacktestRequest(metadata[0].plugin_name, "test", metadata[0].defaults(), date(2025, 1, 1), date(2025, 12, 31), 1e6, 10, "weekly")

    def run(request):
        captured.append(request)
        return SimpleNamespace(output_dir=root / "runs" / "spy", result=SimpleNamespace(
            summary={"initial_cash": request.initial_cash, "metrics_reliable": False},
            nav=pd.DataFrame({"trade_date": [pd.Timestamp("2025-01-02")], "equity": [request.initial_cash]}),
            fills=pd.DataFrame(), positions=pd.DataFrame(), run_id="spy"))

    service = SimpleNamespace(default_request=lambda: defaults, available_strategies=lambda: catalog.metadata(),
                              run=run, runs_root=root / 'runs', user_strategy_plugins={})
    for module in [workspace, backtests]:
        monkeypatch.setattr(module, "build_backtest_service", lambda _: service)
        monkeypatch.setattr(module, "local_data_bounds", lambda: (date(2020, 1, 1), date(2026, 1, 1)))
        monkeypatch.setattr(module, "user_risk_limits", lambda _: RiskLimits())
        monkeypatch.setattr(module, "security_names", lambda: {})
    monkeypatch.setattr(runtime, "get_conn", connect)
    return client, connect, captured, catalog, service


def create_template(client, style='aggressive'):
    template = beginner_templates()[0]
    response = client.post('/api/v1/packages', json={
        'definition': {'name': 'placeholder', 'entry_rules': []},
        'top_n': 7, 'rebalance': 'monthly', 'source': f'template:{template.template_id}', 'style': style})
    assert response.status_code == 201, response.text
    return response.json(), template.presets[style].definition.to_dict()


def payload(strategy):
    return {'strategy': strategy, 'market': '当前股票池', 'from_date': '2025-01-01',
            'to_date': '2025-12-31', 'initial_capital': 250000, 'max_positions': 3, 'rebalance': 'daily'}


def test_template_creation_and_copy_keep_the_chosen_rules(workflow):
    client, connect, captured, *_ = workflow
    saved, expected = create_template(client)
    with connect() as conn:
        stored = json.loads(conn.execute('SELECT definition FROM strategy_packages').fetchone()[0])
    assert stored == expected
    copied = client.post(f"/api/v1/packages/{saved['package_id']}/copy", json={}).json()
    assert copied['definition']['entry_rules'] == saved['definition']['entry_rules']
    assert not captured  # Saving and copying must never execute a backtest.


def test_unified_package_execution_honors_and_records_common_settings(workflow):
    client, _, captured, *_ = workflow
    saved, expected = create_template(client)
    reference = f"package:{saved['package_id']}"
    response = client.post('/api/v1/backtests', json=payload(reference))
    assert response.status_code == 201, response.text
    request = captured[0]
    assert (request.initial_cash, request.top_n, request.rebalance, request.risk_limits.max_positions) == (250000, 3, 'daily', 3)
    assert json.loads(request.strategy_parameters['definition_json']) == expected
    detail = client.get(f"/api/v1/backtests/{response.json()['id']}").json()
    assert detail['market'] == '当前股票池'
    assert detail['result']['effective_config']['strategy_reference'] == reference
    record = client.get('/api/v1/runs').json()['items'][0]
    assert record['backtest_id'] == response.json()['id'] and record['strategy_reference'] == reference


@pytest.mark.parametrize('change', [{'initial_cash': 0}, {'initial_cash': -2}, {'top_n': 0},
    {'top_n': 51}, {'rebalance': 'yearly'}, {'from_date': 'invalid'},
    {'from_date': '2025-12-31', 'to_date': '2025-01-01'}, {'from_date': '2030-01-01', 'to_date': '2031-01-01'}])
def test_legacy_package_endpoint_rejects_invalid_config_without_execution(workflow, change):
    client, _, captured, *_ = workflow
    saved, _ = create_template(client)
    response = client.post(f"/api/v1/packages/{saved['package_id']}/backtest", json=change)
    assert response.status_code == 422, response.text
    assert not captured


def test_unavailable_and_foreign_saved_strategies_never_fall_back(workflow):
    client, connect, captured, *_ = workflow
    saved, _ = create_template(client)
    with connect() as conn:
        conn.execute('UPDATE strategy_packages SET user_id = 2')
    assert client.post('/api/v1/backtests', json=payload(f"package:{saved['package_id']}")).status_code == 404
    assert client.post('/api/v1/backtests', json=payload('user:missing')).status_code == 422
    assert not captured


def test_two_chinese_named_python_assets_remain_distinct_and_reach_their_plugins(workflow):
    client, _, captured, catalog, service = workflow
    assets = []
    for name in ['测试策略甲', '测试策略乙']:
        response = client.post('/api/v1/user-strategies', json={'code': STARTER_STRATEGY_CODE,
            'display_name': name, 'risk_acknowledged': True})
        assert response.status_code == 201, response.text
        assets.append(response.json())
    assert assets[0]['plugin_name'] != assets[1]['plugin_name']
    assert len(client.get('/api/v1/user-strategies').json()['strategies']) == 2
    assert not runtime._register_user_strategies(catalog, 1, service.user_strategy_plugins)
    items = client.get('/api/v1/backtests/catalog').json()['items']
    for asset in assets:
        reference = f"user:{asset['plugin_name']}"
        item = next(i for i in items if i['value'] == reference)
        assert item['label'] == f"{asset['display_name']} · Python"
        assert {p['name'] for p in item['parameters']} == {'fast', 'slow', 'momentum'}
        response = client.post('/api/v1/backtests', json={**payload(reference), 'strategy_parameters': {'fast': 8}})
        assert response.status_code == 201, response.text
        assert captured[-1].strategy_plugin == service.user_strategy_plugins[asset['plugin_name']]
        assert captured[-1].strategy_parameters['fast'] == 8
    assert captured[0].strategy_plugin != captured[1].strategy_plugin
    assert client.post('/api/v1/backtests', json={**payload(reference), 'strategy_parameters': {'typo': 8}}).status_code == 422
    assert len(captured) == 2
