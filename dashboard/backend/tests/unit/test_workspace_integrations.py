"""Provider contract and authenticated API regression tests (no external services)."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.agents_bridge.llm_settings import LLMSettingsStore
from quant_platform.jev import JevClient, ChoiceRequest, NoulRequest, ScoreRequest
from quant_platform.weknora import WeKnoraClient


def response(data):
    result = MagicMock()
    result.__enter__.return_value = result
    result.json.return_value = data
    return result


def test_jev_provider_contract():
    client = JevClient(api_key='test')
    with patch('quant_platform.jev.client.requests.post') as post:
        post.return_value = response({'answers': {'decision': {
            'type': 'choice', 'choice': 'A', 'confidence': .8, 'probabilities': {'A': .8, 'B': .2}}}})
        result = client.choice(ChoiceRequest('选哪个', ['A', 'B'], {'trend': 'up'}))
        assert not result.mock and result.selected == 'A'
        payload = post.call_args.kwargs['json']
        assert payload['state'] == {'trend': 'up'}
        assert payload['questions']['decision'] == {
            'type': 'choice', 'instructions': '选哪个', 'criteria': {'A': 'A', 'B': 'B'}}
        post.return_value = response({'answers': {'decision': {'type': 'noul', 'noul': .9}}})
        result = client.noul(NoulRequest('成立吗'))
        assert result.probability == .9 and result.confidence is None
        post.return_value = response({'answers': {'decision': {
            'type': 'score', 'score': .25, 'confidence': .7, 'probabilities': {'0': .75, '1': .25}}}})
        result = client.score(ScoreRequest('风险', ['低', '高']))
        assert result.level_probabilities == {'低': .75, '高': .25}
        assert result.to_score_0_100() == 25


def test_configured_jev_does_not_fabricate_success():
    with patch.object(JevClient, '_post', return_value={'answers': {}}):
        with pytest.raises(ValueError):
            JevClient(api_key='test').choice(ChoiceRequest('选哪个', ['A', 'B']))
    assert JevClient().choice(ChoiceRequest('选哪个', ['A', 'B'])).mock


def test_weknora_search_and_empty_real_library():
    client = WeKnoraClient('http://localhost:8080/api/v1/', 'test')
    with patch('quant_platform.weknora.client.requests.request') as request:
        request.return_value = response({'success': True, 'data': []})
        assert client.list_knowledge_bases() == []
        assert request.call_args.args[1] == 'http://localhost:8080/api/v1/knowledge-bases'
        assert request.call_args.kwargs['headers']['X-API-Key'] == 'test'
        request.return_value = response({'success': True, 'data': [
            {'knowledge_title': '报告', 'content': '行情数据', 'knowledge_id': 'doc-1'}]})
        refs = client.query('行情', 'kb-1', 1)
        assert refs[0]['title'] == '报告' and refs[0]['snippet'] == '行情数据'
        assert request.call_args.args[1].endswith('/knowledge-search')
        assert request.call_args.kwargs['json']['knowledge_base_id'] == 'kb-1'


def test_weknora_stream_and_references():
    events = [
        {'response_type': 'references', 'knowledge_references': [{'knowledge_title': '报告', 'content': '来源'}]},
        {'response_type': 'answer', 'content': '回答'},
        {'response_type': 'answer', 'content': '内容'},
        {'response_type': 'complete'},
    ]
    stream = response({})
    stream.iter_lines.return_value = [line for event in events
                                    for line in ['event: message', 'data: ' + json.dumps(event), '']]
    client = WeKnoraClient('http://localhost:8080', 'test')
    with patch.object(client, '_request', return_value={'id': 's-1'}), \
         patch('quant_platform.weknora.client.requests.post', return_value=stream) as post:
        result = client.chat('问题', 'kb-1')
        assert result['answer'] == '回答内容' and not result['mock']
        assert result['references'][0]['snippet'] == '来源'
        assert post.call_args.args[0].endswith('/knowledge-chat/s-1')
        assert post.call_args.kwargs['json']['knowledge_base_ids'] == ['kb-1']
        stream.iter_lines.return_value = ['data: ' + json.dumps(events[1]), '']
        with pytest.raises(ValueError, match='interrupted'):
            client.chat('问题', 'kb-1')


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace, '_llm_store', lambda uid: LLMSettingsStore(tmp_path / str(uid) / 'llm.json'))
    for name in ['OPENROUTER_API_KEY', 'WEKNORA_API_KEY', 'WEKNORA_BASE_URL']:
        monkeypatch.delenv(name, raising=False)
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {'id': 1}
    return TestClient(app), app


def test_api_settings_preserve_secrets_and_isolate_users(api):
    client, app = api
    assert client.post('/api/v1/weknora/settings', json={'base_url': 'http://localhost:8080', 'api_key': 'secret'}).status_code == 200
    assert client.post('/api/v1/weknora/settings', json={'base_url': 'http://localhost:8081', 'api_key': ''}).status_code == 200
    assert workspace._weknora_resolve(1) == ('http://localhost:8081', 'secret')
    assert 'secret' not in client.get('/api/v1/weknora/settings').text
    assert client.post('/api/v1/jev/settings', json={'api_key': 'secret'}).status_code == 200
    assert client.post('/api/v1/jev/settings', json={'model': 'typesafe/jev-1.13', 'api_key': ''}).status_code == 200
    assert workspace._jev_client(1).api_key == 'secret'
    assert 'secret' not in client.get('/api/v1/jev/settings').text
    app.dependency_overrides[get_current_user] = lambda: {'id': 2}
    assert not client.get('/api/v1/jev/settings').json()['configured']
    assert not client.get('/api/v1/weknora/settings').json()['configured']


def test_api_validation_demo_and_upstream_failure(api):
    client, app = api
    assert client.post('/api/v1/jev/decide', json={'type': 'choice', 'question': 'Q', 'options': ['A', 'B']}).json()['mock']
    assert client.post('/api/v1/jev/decide', json={'type': 'choice', 'options': ['A']}).status_code == 422
    assert client.post('/api/v1/jev/decide', json={'type': 'score', 'question': 'Q', 'levels': ['L', 'L']}).status_code == 422
    assert client.post('/api/v1/weknora/settings', json={'base_url': 'file:///tmp'}).status_code == 422
    assert client.get('/api/v1/weknora/knowledge-bases').json()['mock']
    with patch.object(WeKnoraClient, 'list_knowledge_bases', side_effect=RuntimeError('private detail')):
        result = client.get('/api/v1/weknora/knowledge-bases')
        assert result.status_code == 502 and 'private detail' not in result.text
    app.dependency_overrides.clear()
    assert client.get('/api/v1/jev/settings').status_code == 401


def test_audit_route_six_dimensions_and_grade_cache(api, tmp_path, monkeypatch):
    """六维审计与选择偏差字段完整透传；评级按记录编号缓存。"""
    import quant_platform.backtest.credibility as credibility_mod
    import quant_platform.backtest.validity as validity_mod
    from quant_platform.backtest.credibility import (
        CredibilityDimension,
        CredibilityReport,
    )
    from quant_platform.backtest.multiple_testing import SelectionBiasResult

    from app.quant import run_evidence
    monkeypatch.setattr(run_evidence, "RUNTIME_ROOT", tmp_path)
    run_dir = tmp_path / "runs" / "r-7"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "validity_report.json").write_text(json.dumps({
        "audit_version": validity_mod.CURRENT_AUDIT_VERSION, "status": "VALID",
        "metrics_reliable": True, "issues": []}), encoding="utf-8")

    dims = tuple(
        CredibilityDimension(key=key, title=key, status="pass", findings=())
        for key in (
            "data_integrity", "lookahead_guard", "sample_bias",
            "cost_realism", "capacity", "selection_bias",
        )
    )
    selection = SelectionBiasResult(
        status="warn", message="本批 10 次尝试，DSR 显著性 62.0%。",
        optimization_id="opt-1", objective="sharpe", trial_count=10, valid_trials=10,
        effective_trials=4, average_correlation=0.7, best_median_gap=0.5,
        dsr=0.62, psr=0.9, benchmark_sharpe=1.2, observed_sharpe=1.5, observations=250,
        evidence=(
            {"运行编号": "r-1", "试验状态": "成功", "可计算": True, "年化 Sharpe": 1.5, "说明": "纳入计算。"},
        ),
    )
    report = CredibilityReport(
        grade="B", headline="整体可信。", dimensions=dims, validity_status="VALID",
        metrics_reliable=True, observations=250, maximum_calendar_gap_days=3,
        total_transaction_cost=100.0, transaction_cost_ratio=0.001, selection_bias=selection,
    )
    row = {
        "id": 7, "strategy": "动量", "from_date": "2024-01-01", "to_date": "2024-12-31",
        "status": "完成", "result": json.dumps({"output_dir": str(run_dir)}),
        "created_at": "2024-01-01T00:00:00",
    }

    class FakeResult:
        def __init__(self, r):
            self.r = r

        def fetchone(self):
            return self.r

        def fetchall(self):
            return [self.r]

    class FakeConn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, *args, **kwargs):
            return FakeResult(row)

    monkeypatch.setattr(workspace, "get_conn", lambda: FakeConn())
    monkeypatch.setattr(credibility_mod, "audit_persisted_run", lambda d: report)
    monkeypatch.setattr(validity_mod, "load_persisted_validity", lambda d: {"issues": []})
    workspace._GRADE_CACHE.clear()

    client, _ = api
    data = client.get("/api/v1/runs/run-7/audit").json()
    assert data["grade"] == "B"
    assert len(data["dimensions"]) == 6
    assert data["dimensions"][-1]["key"] == "selection_bias"
    bias = data["selection_bias"]
    assert bias["trial_count"] == 10 and abs(bias["dsr"] - 0.62) < 1e-9
    assert bias["scope_note"] and bias["evidence"][0]["运行编号"] == "r-1"

    items = client.get("/api/v1/runs/audit").json()["items"]
    assert items[0]["run_id"] == "run-7" and items[0]["grade"] == "B"
    # 运行不可变：评级缓存后不重算。
    monkeypatch.setattr(credibility_mod, "audit_persisted_run", lambda d: pytest.fail("不应重算"))
    items = client.get("/api/v1/runs/audit").json()["items"]
    assert items[0]["grade"] == "B"
