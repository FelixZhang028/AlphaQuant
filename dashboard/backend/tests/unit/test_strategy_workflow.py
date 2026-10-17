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
from test_research_integrity import api, save_run


@pytest.fixture
def workflow(api, monkeypatch):
    client, connect, root = api
    with connect() as conn:
        conn.execute("CREATE TABLE strategy_packages (id INTEGER PRIMARY KEY, user_id INTEGER, package_id TEXT, name TEXT, definition TEXT, top_n INTEGER, rebalance TEXT, source TEXT, created_at TEXT)")
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
                              run=run, runs_root=root / 'runs')
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
    assert client.post('/api/v1/backtests', json=payload('no_such_strategy')).status_code == 422
    assert not captured


def test_python_strategies_are_gone_and_old_references_explain_why(workflow):
    # 用户写的 Python 代码不再在服务器上运行：没有保存、预览的接口，目录里也没有 Python 策略。
    client, _, captured, *_ = workflow
    code = 'print(1)'
    assert client.post('/api/v1/user-strategies', json={'code': code, 'display_name': 'x'}).status_code in (404, 405)
    assert client.post('/api/v1/user-strategies/preview', json={'code': code}).status_code in (404, 405)
    assert client.get('/api/v1/user-strategies').status_code in (404, 405)
    items = client.get('/api/v1/backtests/catalog').json()['items']
    assert items and not any(i['value'].startswith('user:') or 'Python' in i['label'] for i in items)
    response = client.post('/api/v1/backtests', json=payload('user:old_strategy'))
    assert response.status_code == 422 and 'Python 策略已经停用' in response.json()['detail']
    assert not captured


def test_options_show_each_templates_real_rules_and_the_window_range_of_every_indicator(workflow):
    client, *_ = workflow
    options = client.get('/api/v1/studio/options').json()
    template = beginner_templates()[0]
    listed = next(item for item in options['templates'] if item['template_id'] == template.template_id)
    assert set(listed['presets']) == set(template.presets)
    preset = listed['presets']['aggressive']
    saved = client.post('/api/v1/packages', json={
        'definition': {**preset['definition'], 'name': '照模板保存'}, 'top_n': preset['top_n'],
        'rebalance': preset['rebalance'], 'source': f'template:{template.template_id}', 'style': 'aggressive'}).json()
    # What the form received from the options is exactly what the engine would run for that template.
    published = template.presets['aggressive'].definition.to_dict()
    with workflow[1]() as conn:
        stored = json.loads(conn.execute('SELECT definition FROM strategy_packages').fetchone()[0])
    assert all(stored[key] == published[key] for key in ('entry_logic', 'entry_rules', 'ranking'))
    assert (saved['name'], saved['source']) == ('照模板保存', f'template:{template.template_id}:aggressive')
    assert options['indicator_windows']['close'] is None
    assert options['indicator_windows']['sma'] == {'default': 20, 'minimum': 2, 'maximum': 500}
    assert set(options['indicator_windows']) == set(options['indicators'])


def test_an_edited_template_is_saved_as_shown_and_labelled_as_modified(workflow):
    client, connect, captured, *_ = workflow
    template = beginner_templates()[0]
    definition = client.get('/api/v1/studio/options').json()['templates'][0]['presets']['balanced']['definition']
    definition = {**definition, 'name': '改过的动量', 'entry_rules': [
        {'left': {'name': 'close'}, 'operator': 'gt', 'right': {'name': 'sma', 'window': 120}}]}
    saved = client.post('/api/v1/packages', json={
        'definition': definition, 'top_n': 4, 'rebalance': 'weekly',
        'source': f'template:{template.template_id}', 'style': 'balanced'})
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body['source'] == f'template_modified:{template.template_id}:balanced'
    assert body['definition']['entry_rules'] == definition['entry_rules']
    assert '收盘价大于120日移动平均线' in body['describe_text']
    # The stored rules, not the template's, are what a later backtest executes.
    run = client.post('/api/v1/backtests', json=payload(f"package:{body['package_id']}"))
    assert run.status_code == 201, run.text
    executed = json.loads(captured[-1].strategy_parameters['definition_json'])
    assert executed['entry_rules'] == [
        {'left': {'name': 'close'}, 'operator': 'greater_than', 'right': {'name': 'moving_average', 'window': 120}}]


def test_the_check_reads_the_rules_back_and_explains_what_is_wrong(workflow):
    client, *_ = workflow
    body = {'definition': {'name': '检查', 'entry_logic': 'any', 'entry_rules': [
        {'left': {'name': 'return_1d', 'window': 60}, 'operator': 'gt', 'value': 0.05},
        {'left': {'name': 'close'}, 'operator': 'gt', 'right': {'name': 'sma', 'window': 60}}],
        'ranking': {'indicator': {'name': 'volatility', 'window': 40}, 'direction': 'ascending'}},
        'top_n': 3, 'rebalance': 'monthly'}
    checked = client.post('/api/v1/packages/preflight', json=body).json()
    assert checked['description'].startswith('每月调仓；只保留满足“60日区间涨跌幅大于5%，或者收盘价大于60日移动平均线”的股票')
    assert '按40日历史波动率从低到高排序，等权持有前3只' in checked['description']
    assert checked['minimum_history_days'] == 61
    body['definition']['entry_rules'][0]['left']['window'] = 9999
    rejected = client.post('/api/v1/packages/preflight', json=body)
    assert rejected.status_code == 422 and '周期必须在1至500之间' in rejected.json()['detail']


def test_rule_descriptions_drop_decimals_that_carry_no_information():
    from quant_platform.strategies.rule_schema import _format_number

    shown = {0: "0", 5: "5", 70: "70", 0.05: "5%", 0.125: "12.5%", -0.05: "-5%", 12.345: "12.35", 1_000_000: "1,000,000"}
    assert {value: _format_number(value) for value in shown} == shown
