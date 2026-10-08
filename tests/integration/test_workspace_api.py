"""New React adapters use isolated storage and preserve existing business rules."""

import io
import json
import sqlite3
import zipfile

import pandas as pd
import pytest
from test_api import completed as completed
from test_api import environment as environment
from test_background_tasks import wait_for

from quant_platform.api.advanced_tasks import execute_advanced, freeze_advanced
from quant_platform.api.common import ApiError
from quant_platform.api.workspace_schemas import XTickInput
from quant_platform.application.data_jobs import DataJobs
from quant_platform.application.research_plans import ResearchPlanStore
from quant_platform.strategies.nl_builder import NLStrategyDraft

PREFIX = "/api/v1"


def test_data_overview_coverage_and_sources_preserve_original_service(environment):
    from quant_platform.api.common import safe_wire, table
    from quant_platform.application.data_service import DataCenterService

    _, _, client, service = environment
    data = DataCenterService(service.app_config_path)
    original = data.overview()
    assert client.get(PREFIX + "/data/overview").json() == safe_wire(original.to_dict())
    assert client.get(PREFIX + "/data/coverage?offset=0&limit=500").json() == safe_wire(table(original.per_symbol, 0, 500))
    assert client.get(PREFIX + "/data/coverage/export.csv").content.decode("utf-8-sig") == original.per_symbol.to_csv(index=False)
    assert client.get(PREFIX + "/data/sources").json() == safe_wire(data.market_source_status())


@pytest.mark.parametrize("name", ["benchmark_bars", "security_master", "data_manifests"])
def test_data_tables_full_export_names_versions_and_empty_state(environment, monkeypatch, name):
    from quant_platform.api.common import safe_wire, table
    from quant_platform.application.data_service import DataCenterService
    from quant_platform.application.manifest_summary import add_provider_route_summary

    _, _, client, service = environment
    repository_type = type(DataCenterService(service.app_config_path).repository)
    if name == "benchmark_bars":
        frame = pd.DataFrame({"symbol": ["000905.SH"] * 605, "trade_date": pd.date_range("2020-01-01", periods=605), "raw_close": range(605)})
    elif name == "security_master":
        frame = pd.DataFrame({"symbol": [f"{i:06}.SZ" for i in range(605)], "name": [f"验收证券{i}" for i in range(605)], "security_type": ["stock"] * 605})
    else:
        frame = pd.DataFrame({"dataset": ["daily_bars"] * 605, "source": ["baostock"] * 605, "version_id": [f"version-{i}" for i in range(605)],
            "completed_at": pd.date_range("2020-01-01", periods=605), "error": ["token=version-secret"] * 605,
            "parameters_json": [json.dumps({"requested_sources": ["akshare", "baostock"], "fallback_enabled": True, "provider_attempts": [{"source": "akshare", "status": "failed"}, {"source": "baostock", "status": "success"}]})] * 605})
    monkeypatch.setattr(repository_type, "read_table", lambda self, requested: frame.copy() if requested == name else pd.DataFrame())
    keys = {"benchmark_bars": ["trade_date", "symbol"], "security_master": ["symbol"], "data_manifests": ["completed_at"]}[name]
    expected = frame.sort_values(keys, ascending=name != "data_manifests")
    if name == "data_manifests":
        expected = pd.DataFrame(safe_wire(add_provider_route_summary(expected))["rows"])
    response = client.get(f"{PREFIX}/data/tables/{name}?offset=200&limit=200")
    assert response.status_code == 200, response.text
    assert response.json() == safe_wire(table(expected, 200, 200))
    exported = client.get(f"{PREFIX}/data/tables/{name}/export.csv")
    assert exported.content.decode("utf-8-sig") == expected.to_csv(index=False)
    assert len(pd.read_csv(io.BytesIO(exported.content))) == 605
    assert "version-secret" not in exported.text
    if name == "data_manifests":
        assert response.json()["rows"][0]["fallback_used"] is True
        assert response.json()["rows"][0]["provider_route"] == "akshare:failed -> baostock:success"
    frame = frame.iloc[:0]
    assert client.get(f"{PREFIX}/data/tables/{name}").json()["total"] == 0


@pytest.mark.parametrize("change", [{"datasets": []}, {"datasets": ["unknown"]}, {"start_date": "2023-05-01"}, {"end_date": "invalid"}])
def test_data_update_rejects_invalid_submissions_before_queue(environment, change):
    _, _, client, _ = environment
    before = client.get(PREFIX + "/tasks").json()["total"]
    body = {"start_date": "2023-01-03", "end_date": "2023-04-28", "datasets": ["daily_bars"], **change}
    assert client.post(PREFIX + "/tasks", json={"kind": "data_update", "input": body}).status_code == 422
    assert client.get(PREFIX + "/tasks").json()["total"] == before


def test_audit_preserves_persisted_evidence_when_current_settings_change(environment, completed, monkeypatch):
    from quant_platform.api.common import safe_wire
    from quant_platform.backtest.credibility import audit_persisted_run

    _, _, client, service = environment
    run_id, _ = completed
    directory = service.runs_root / run_id
    expected = safe_wire(audit_persisted_run(directory))
    assert len(expected["dimensions"]) == 6
    monkeypatch.setitem(service.configs, "execution", {"execution": {"max_participation_rate": 0.9, "slippage_bps": 9999}})
    monkeypatch.setattr("quant_platform.api.dependencies.ApiContext.backtests", lambda self: service)
    response = client.get(f"{PREFIX}/runs/{run_id}/audit")
    assert response.status_code == 200
    assert {key: response.json()[key] for key in expected} == expected
    execution = service.run_store.load_config(run_id)["execution"]["execution"]
    assert response.json()["execution_assumptions"]["rows"] == [
        {"审计假设": "历史分期费率", "取值": "启用" if execution.get("historical_fees") else "停用" if execution.get("historical_fees") is False else "未记录"},
        {"审计假设": "参与率上限", "取值": f"{execution['max_participation']:.1%}" if execution.get("max_participation") is not None else "未记录"},
        {"审计假设": "滑点率", "取值": f"{execution['slippage_rate']:.3%}" if execution.get("slippage_rate") is not None else "未记录"},
        {"审计假设": "未知状态策略", "取值": execution.get("unknown_status_policy", "未记录")},
    ]
    from quant_platform.backtest.validity import load_persisted_validity
    assert response.json()["validity"] == safe_wire(load_persisted_validity(directory))
    snapshot = directory / "config.snapshot.yaml"
    snapshot_backup = snapshot.read_bytes()
    try:
        import yaml
        frozen = yaml.safe_load(snapshot_backup)
        frozen["execution"]["execution"].update(historical_fees=True, max_participation=0.125, slippage_rate=0.00123, unknown_status_policy="reject")
        snapshot.write_text(yaml.safe_dump(frozen), encoding="utf-8")
        assert [row["取值"] for row in client.get(f"{PREFIX}/runs/{run_id}/audit").json()["execution_assumptions"]["rows"]] == ["启用", "12.5%", "0.123%", "reject"]
        snapshot.unlink()
        assert all(row["取值"] == "未记录" for row in client.get(f"{PREFIX}/runs/{run_id}/audit").json()["execution_assumptions"]["rows"])
    finally:
        snapshot.write_bytes(snapshot_backup)
    summary = directory / "summary.json"
    backup = summary.read_bytes()
    try:
        summary.unlink()
        missing = client.get(f"{PREFIX}/runs/{run_id}/audit")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "result_missing"
    finally:
        summary.write_bytes(backup)


@pytest.mark.parametrize("use_cache", [False, True])
def test_ai_analysis_freezes_all_knowledge_and_cuts_history_at_analysis_date(environment, monkeypatch, use_cache):
    from dataclasses import make_dataclass
    from datetime import date
    from quant_platform.api.ai_tasks import execute_ai, freeze_ai
    from quant_platform.api.task_schemas import AIInput
    from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore

    _, app, _, _ = environment
    ctx = app.state.context
    knowledge = PriorKnowledgeStore(ctx.prior_path)
    one = knowledge.add("不能忽略成本", "观点甲")
    two = knowledge.add("检查样本偏差", "观点乙")
    try:
        body = AIInput(symbol="000001", trade_date=date(2023, 4, 28), lookback_days=25,
            provider="mock", debate_rounds=2, use_cache=use_cache, news_sources=["eastmoney", "cls"])
        frozen = freeze_ai(body, ctx)
        assert frozen["symbol"] == "000001.SZ"
        assert "不能忽略成本" in frozen["prior_knowledge"] and "检查样本偏差" in frozen["prior_knowledge"]
        calls = []
        decision = {"action": "HOLD", "symbol": frozen["symbol"]}
        State = make_dataclass("EvidenceState", ["decision", "news_report", "fill"])
        state = State(decision, "新闻源失败后保留其他证据", {"stop_loss": 10.5, "target_price": 14.0})
        class Runner:
            def __init__(self, **kwargs):
                assert kwargs["debate_rounds"] == 2 and kwargs["news_sources"] == ("eastmoney", "cls")
                assert kwargs["prior_knowledge"] == frozen["prior_knowledge"]
            def check(self, symbol, trade_date, history):
                assert symbol == "000001.SZ" and trade_date == body.trade_date
                assert len(history) == 25 and history.trade_date.max().date() <= body.trade_date
                assert history.trade_date.is_monotonic_increasing
            def decide(self, symbol, trade_date, history):
                self.check(symbol, trade_date, history); calls.append("cached"); return decision
            def decide_full(self, symbol, trade_date, history, **kwargs):
                self.check(symbol, trade_date, history); calls.append("full"); return state
        monkeypatch.setattr("quant_platform.agents_bridge.AgentRunner", Runner)
        monkeypatch.setattr(ctx, "progress", lambda *args: None)
        result = execute_ai(body, ctx, frozen, None, "controlled-analysis")
        assert result["decision"] == decision
        assert calls == (["cached"] if use_cache else ["full"])
        assert result["state"] is None if use_cache else result["state"]["fill"] == {"stop_loss": 10.5, "target_price": 14.0}
    finally:
        knowledge.delete(one.id)
        knowledge.delete(two.id)


@pytest.mark.parametrize("change", [{"symbol": ""}, {"symbol": "非法代码"}, {"lookback_days": 19}, {"debate_rounds": 5}, {"trade_date": "invalid"}, {"provider": "not-a-provider"}])
def test_ai_invalid_inputs_and_unknown_provider_do_not_enqueue(environment, change):
    _, _, client, _ = environment
    body = {"symbol": "000001", "trade_date": "2023-04-28", "provider": "mock", **change}
    before = client.get(PREFIX + "/tasks").json()["total"]
    assert client.post(PREFIX + "/tasks", json={"kind": "ai_analysis", "input": body}).status_code == 422
    assert client.get(PREFIX + "/tasks").json()["total"] == before


def test_ai_missing_model_credentials_are_rejected_before_queue(environment, monkeypatch):
    _, _, client, _ = environment
    class EmptySettings:
        def resolve(self, provider): return {"base_url": "", "model": "", "api_key": ""}
    monkeypatch.setattr("quant_platform.api.workspace.settings_store", lambda ctx: EmptySettings())
    response = client.post(PREFIX + "/tasks", json={"kind": "ai_analysis", "input": {
        "symbol": "000001", "trade_date": "2023-04-28", "provider": "openai",
    }})
    assert response.status_code == 409 and response.json()["error"]["code"] == "model_not_ready"


def test_settings_never_return_saved_credentials(environment, monkeypatch):
    _, app, client, _ = environment
    monkeypatch.setenv("XTICK_TOKEN", "environment-secret")
    response = client.post(
        PREFIX + "/settings/models/custom",
        json={
            "base_url": "http://127.0.0.1:12345/v1",
            "model": "test-model",
            "api_key": "test-model-secret",
            "set_default": False,
        },
    )
    assert response.status_code == 200, response.text
    assert (
        client.post(
            PREFIX + "/settings/data/xtick", json={"token": "test-token-secret"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            PREFIX + "/settings/models/custom", json={"base_url": "", "model": "other"}
        ).status_code
        == 200
    )
    assert (
        client.post(
            PREFIX + "/settings/proxy", json={"enabled": False, "address": "http://127.0.0.1:7897"}
        ).status_code
        == 200
    )
    value = client.get(PREFIX + "/settings")
    assert value.status_code == 200
    assert "test-model-secret" not in value.text and "test-token-secret" not in value.text
    assert value.json()["default_provider"] == "mock"
    assert next(p for p in value.json()["providers"] if p["key"] == "custom")["key_configured"]
    assert client.get(PREFIX + "/settings/system").status_code == 200
    assert (
        client.post(PREFIX + "/settings/data/xtick", json={"password": "invalid"}).status_code
        == 422
    )


def test_risk_validation_and_historical_snapshot(environment, completed):
    _, _, client, _ = environment
    run_id, _ = completed
    original = client.get(f"{PREFIX}/runs/{run_id}/request").json()["request"]["risk_limits"]
    limits = client.get(PREFIX + "/risk").json()
    limits["max_single_weight"] = 0.75
    response = client.post(PREFIX + "/risk", json=limits)
    assert response.status_code == 200, response.text
    assert client.get(PREFIX + "/risk").json()["max_single_weight"] == 0.75
    assert (
        client.get(f"{PREFIX}/runs/{run_id}/request").json()["request"]["risk_limits"] == original
    )
    limits["max_single_weight"] = 3
    assert client.post(PREFIX + "/risk", json=limits).status_code == 422


def test_python_safety_register_load_and_delete(environment):
    _, _, client, _ = environment
    unsafe = {"code": "open('unwanted-file', 'w')"}
    assert client.post(PREFIX + "/strategies/python", json=unsafe).status_code == 409
    starter = client.get(PREFIX + "/strategies/python").json()["starter"]
    response = client.post(
        PREFIX + "/strategies/python", json={"code": starter, "risk_acknowledged": True}
    )
    assert response.status_code == 201, response.text
    plugin = response.json()["plugin_name"]
    items = client.get(PREFIX + "/strategies/python").json()["items"]
    assert next(v for v in items if v["plugin_name"] == plugin)["code"] == starter
    assert plugin in {v["plugin_name"] for v in client.get(PREFIX + "/strategies").json()["items"]}
    assert client.delete(PREFIX + "/strategies/python/../escape").status_code == 404
    assert client.delete(PREFIX + "/strategies/python/" + plugin).status_code == 204


def test_custom_factor_is_shared_with_catalog_evaluation_and_worker(environment):
    _, _, client, _ = environment
    body = {
        "name": "api_custom_factor",
        "display_name": "测试自定义动量",
        "field": "adjusted_close",
        "operator": "momentum",
        "window": 10,
    }
    response = client.post(PREFIX + "/factors/custom", json=body)
    assert response.status_code == 201, response.text
    assert client.post(PREFIX + "/factors/custom", json=body).status_code == 409
    assert body["name"] in {
        f["name"] for f in client.get(PREFIX + "/factors/catalog").json()["items"]
    }
    job = client.post(
        PREFIX + "/tasks",
        json={
            "kind": "factor_evaluation",
            "input": {
                "factor_name": body["name"],
                "start_date": "2023-01-03",
                "end_date": "2023-04-28",
            },
        },
    )
    assert job.status_code == 202, job.text
    assert wait_for(client, job.json()["id"])["status"] == "SUCCESS"
    assert client.delete(PREFIX + "/factors/custom/" + body["name"]).status_code == 204


def test_plan_restores_execution_and_links_actual_run(environment, completed):
    root, app, client, service = environment
    run_id, direct = completed
    saved = client.post(PREFIX + "/research/plans", json={"title": "历史执行", "run_id": run_id})
    assert saved.status_code == 201, saved.text
    plan = saved.json()
    restored = client.get(f"{PREFIX}/research/plans/{plan['plan_id']}/{plan['revision']}/request")
    assert restored.status_code == 200, restored.text
    body = restored.json()["request"]
    assert body["plan_id"] == plan["plan_id"] and body["plan_revision"] == plan["revision"]
    assert client.post(PREFIX + "/backtests/inspect", json=body).json()["ready"]
    body["strategy_id"] = "restored_plan_run"
    task = client.post(
        PREFIX + "/tasks", json={"kind": "backtest", "input": {"request": body, "confirmed": True}}
    )
    assert task.status_code == 202, task.text
    identifier = task.json()["id"]
    assert wait_for(client, identifier)["status"] == "SUCCESS"
    result = client.get(f"{PREFIX}/tasks/{identifier}/result").json()
    versions = client.get(PREFIX + "/research/plans").json()["items"]
    linked = next(v for v in versions if result["run_id"] in v["runs"])
    assert linked["plan_id"] == plan["plan_id"] and linked["revision"] > plan["revision"]
    comparison = client.post(
        PREFIX + "/research/plans/compare",
        json={
            "versions": [
                {"plan_id": plan["plan_id"], "revision": plan["revision"]},
                {"plan_id": linked["plan_id"], "revision": linked["revision"]},
            ]
        },
    )
    assert comparison.status_code == 200 and comparison.json()["differences"]["rows"]
    assert all(row["summary"] is not None for row in comparison.json()["results"])


def test_external_evidence_errors_and_duplicate_confirmation(environment):
    _, _, client, _ = environment
    content = "日期,股票代码,买卖方向,成交数量,成交价\n2023-01-03,000001,买入,100,12.5"
    preview = client.post(PREFIX + "/audits/external/preview", json={"content": content})
    assert preview.status_code == 200 and len(preview.json()["mapping"]) == 5
    body = {"content": content, "mapping": preview.json()["mapping"]}
    result = client.post(PREFIX + "/audits/external/check", json=body)
    assert result.status_code == 200, result.text
    assert result.json()["findings"]["rows"] and result.json()["markdown"]
    duplicated = content + "\n2023-01-03,000001,买入,100,12.5"
    assert (
        client.post(
            PREFIX + "/audits/external/check", json={**body, "content": duplicated}
        ).status_code
        == 409
    )
    assert (
        client.post(
            PREFIX + "/audits/external/check",
            json={**body, "content": duplicated, "duplicate_confirmed": True},
        ).status_code
        == 200
    )
    assert (
        client.post(
            PREFIX + "/audits/external/check", json={"content": content.replace("12.5", "unknown")}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("unit", ["股", "手"])
@pytest.mark.parametrize("raw_prices", [True, False])
def test_external_evidence_matches_original_rules_and_units(environment, unit, raw_prices):
    from quant_platform.api.common import safe_wire
    from quant_platform.forensics.checks import check_trades, load_evidence, markdown_report
    from quant_platform.forensics.parsing import read_material, detect_columns, parse_trades

    _, _, client, service = environment
    content = "日期,股票代码,买卖方向,成交数量,成交价\n2023-01-03,000001,买入,100,12.5\n\n2023-01-03,600999,卖出,200,20"
    frame = read_material(content)
    mapping = detect_columns(frame)
    parsed = parse_trades(frame, mapping, unit)
    assert parsed.errors.empty
    assert parsed.trades.quantity.tolist() == ([100, 200] if unit == "股" else [10000, 20000])
    master, bars = load_evidence(environment[0] / "market", parsed.trades)
    expected = check_trades(parsed.trades, master, bars, raw_prices)
    response = client.post(PREFIX + "/audits/external/check", json={
        "content": content, "mapping": mapping, "unit": unit, "raw_prices": raw_prices,
    })
    assert response.status_code == 200, response.text
    actual = response.json()
    assert actual["findings"] == safe_wire(expected)
    assert actual["markdown"] == markdown_report(expected)
    assert actual["counts"] == expected["结论"].value_counts().to_dict()
    assert set(expected["表格行"]) == {2, 4}
    assert expected.loc[expected["股票"].eq("600999.SH"), "结论"].eq("证据不足").all()
    invalid = client.post(PREFIX + "/audits/external/check", json={
        "content": content.replace("200,20", "200,unknown"), "mapping": mapping,
    })
    assert invalid.status_code == 422
    assert invalid.json()["error"]["details"]["rows"][0]["表格行"] == 4


@pytest.mark.parametrize("status", ["STARTING", "RUNNING", "RETRYING", "SUCCESS", "PARTIAL", "FAILED", "STOPPED", "INTERRUPTED"])
def test_backfill_retry_status_and_original_range(environment, monkeypatch, status):
    from datetime import date

    _, _, client, _ = environment
    record = {"id": "status-job", "status": status, "start_date": "2022-07-01", "end_date": "2023-04-28", "datasets": ["bars", "derived"]}
    calls = []
    monkeypatch.setattr(DataJobs, "records", lambda self: [record])
    def start(self, start_date, end_date, datasets):
        calls.append((start_date, end_date, datasets))
        return {"id": "continued-job"}
    monkeypatch.setattr(DataJobs, "start", start)
    assert client.get(PREFIX + "/data/backfill/jobs").json()["items"] == [record]
    response = client.post(PREFIX + "/data/backfill/jobs/status-job/retry")
    if status in {"PARTIAL", "FAILED", "STOPPED", "INTERRUPTED"}:
        assert response.status_code == 202, response.text
        assert calls == [(date(2022, 7, 1), date(2023, 4, 28), ["bars", "derived"])]
    else:
        assert response.status_code == 409
        assert calls == []


def test_factor_combination_freezes_spec_and_detects_changed_factor(environment):
    _, _, client, _ = environment
    custom = {
        "name": "api_combination_factor", "display_name": "组合版本验收",
        "field": "adjusted_close", "operator": "momentum", "window": 20,
    }
    assert client.post(PREFIX + "/factors/custom", json=custom).status_code == 201
    body = {
        "factor_names": ["momentum_20", custom["name"]],
        "train_start": "2022-07-01",
        "train_end": "2022-12-30",
        "test_start": "2023-01-03",
        "test_end": "2023-04-28",
    }
    response = client.post(PREFIX + "/tasks", json={"kind": "factor_combination", "input": body})
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    assert wait_for(client, identifier)["status"] == "SUCCESS"
    result = client.get(f"{PREFIX}/tasks/{identifier}/result").json()
    assert len(result["spec"]) == 2 and result["factor_fingerprint"]
    prepared = client.post(PREFIX + "/factors/combinations/prepare", json={"task_id": identifier})
    assert prepared.status_code == 200, prepared.text
    request = prepared.json()["request"]
    assert request["strategy_plugin"] == "factor_composite"
    assert json.loads(request["strategy_parameters"]["factors_json"]) == result["spec"]
    assert client.delete(PREFIX + "/factors/custom/" + custom["name"]).status_code == 204
    assert client.post(PREFIX + "/factors/custom", json={**custom, "window": 30}).status_code == 201
    changed = client.post(PREFIX + "/factors/combinations/prepare", json={"task_id": identifier})
    assert changed.status_code == 409 and changed.json()["error"]["code"] == "factor_changed"
    assert client.delete(PREFIX + "/factors/custom/" + custom["name"]).status_code == 204
    missing = client.post(PREFIX + "/factors/combinations/prepare", json={"task_id": identifier})
    assert missing.status_code == 409 and missing.json()["error"]["code"] == "factor_changed"


def test_ai_chat_uses_completed_analysis_and_persistent_history(environment, monkeypatch):
    _, _, client, _ = environment
    response = client.post(
        PREFIX + "/tasks",
        json={
            "kind": "ai_analysis",
            "input": {
                "symbol": "000001",
                "trade_date": "2023-04-28",
                "provider": "mock",
                "use_cache": False,
            },
        },
    )
    identifier = response.json()["id"]
    assert wait_for(client, identifier)["status"] == "SUCCESS"
    chat = client.post(
        PREFIX + "/tasks",
        json={
            "kind": "ai_chat",
            "input": {"analysis_task_id": identifier, "message": "解释你的风险依据"},
        },
    )
    assert chat.status_code == 202, chat.text
    first = chat.json()["id"]
    assert wait_for(client, first)["status"] == "SUCCESS"
    second = client.post(
        PREFIX + "/tasks",
        json={
            "kind": "ai_chat",
            "input": {
                "analysis_task_id": identifier,
                "message": "还应注意什么",
                "previous_task_id": first,
            },
        },
    )
    assert second.status_code == 202, second.text
    second_id = second.json()["id"]
    assert wait_for(client, second_id)["status"] == "SUCCESS"
    assert len(client.get(f"{PREFIX}/tasks/{second_id}/result").json()["messages"]) == 4
    _, app, _, _ = environment
    monkeypatch.setattr("quant_platform.api.background.TaskManager.ensure_worker", lambda *args: None)
    other = client.post(PREFIX + "/tasks", json={"kind": "ai_analysis", "input": {
        "symbol": "600000", "trade_date": "2023-04-28", "provider": "mock", "use_cache": False,
    }}).json()["id"]
    pending = client.post(PREFIX + "/tasks", json={"kind": "ai_chat", "input": {"analysis_task_id": other, "message": "尚未完成"}})
    assert pending.status_code == 409 and pending.json()["error"]["code"] == "analysis_required"
    app.state.context.tasks.store.finish(other, "SUCCESS", result=app.state.context.tasks.store.result(identifier))
    crossed = client.post(PREFIX + "/tasks", json={"kind": "ai_chat", "input": {"analysis_task_id": other, "message": "不得跨研究", "previous_task_id": first}})
    assert crossed.status_code == 409 and crossed.json()["error"]["code"] == "chat_context"


@pytest.mark.parametrize("compressed", [False, True])
@pytest.mark.parametrize("remote_error", [False, True])
def test_xtick_whitelist_zip_json_and_private_token(environment, monkeypatch, compressed, remote_error):
    _, app, client, _ = environment
    ctx = app.state.context
    monkeypatch.setenv("XTICK_TOKEN", "private-test-token")
    body = XTickInput(category_id=1, api_id=101, parameters={"symbol": "all"})
    frozen = freeze_advanced("xtick_query", body, ctx)
    payload = [{"code": "000001", "name": "测试"}]
    envelope = {"code": 403, "message": "private-test-token"} if remote_error else {"code": 200, "data": payload}
    content = json.dumps(envelope).encode()
    if compressed:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("data.json", content)
        content = buffer.getvalue()

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return envelope

    response = Response()
    response.content = content
    monkeypatch.setattr("quant_platform.api.advanced_tasks.requests.get", lambda *a, **k: response)
    ctx.progress = lambda *args: None
    if remote_error:
        with pytest.raises(ApiError) as error:
            execute_advanced("xtick_query", body.model_dump(), ctx, {"advanced": frozen})
        assert error.value.code == "xtick_remote"
        assert "private-test-token" not in str(error.value)
    else:
        result = execute_advanced("xtick_query", body.model_dump(), ctx, {"advanced": frozen})
        assert result["table"]["total"] == 1 and result["raw"] == payload
        assert "private-test-token" not in json.dumps(result)
    catalog = client.get(PREFIX + "/data/xtick/catalog").json()["items"]
    assert sum(len(c["docApis"]) for c in catalog) == 85
    assert all(p["name"] != "token" for c in catalog for a in c["docApis"] for p in a["inputParas"])
    with pytest.raises(ApiError):
        freeze_advanced(
            "xtick_query", XTickInput(category_id=1, api_id=101, parameters={"token": "bad"}), ctx
        )


def test_backfill_adapters_share_existing_supervisor(environment, monkeypatch):
    _, _, client, _ = environment
    monkeypatch.setattr(
        DataJobs,
        "records",
        lambda self: [
            {
                "id": "sample-job",
                "status": "PARTIAL",
                "start_date": "2023-01-03",
                "end_date": "2023-04-28",
                "datasets": ["bars"],
            }
        ],
    )
    monkeypatch.setattr(
        DataJobs,
        "start",
        lambda self, start, end, datasets: {"id": "new-job", "datasets": datasets},
    )
    monkeypatch.setattr(DataJobs, "log", lambda self, identifier: "api_key=test-secret")
    assert client.get(PREFIX + "/data/backfill/jobs").status_code == 200
    assert client.post(PREFIX + "/data/backfill/jobs/sample-job/retry").json()["id"] == "new-job"
    assert "test-secret" not in client.get(PREFIX + "/data/backfill/jobs/sample-job/log").text


def test_analytics_and_all_status_filter(environment, completed):
    _, _, client, _ = environment
    run_id, direct = completed
    analytics = client.get(f"{PREFIX}/runs/{run_id}/analytics")
    assert analytics.status_code == 200, analytics.text
    assert analytics.json()["normalized"]["rows"][0]["equity"] == 1
    assert analytics.json()["monthly"]["rows"]
    assert client.get(PREFIX + "/runs?include_all_status=true").json()["total"] >= 1


def test_chart_contract_preserves_benchmark_gaps_and_calendar_months(environment):
    _, _, client, service = environment
    path = service.runs_root / "analytics-contract"
    path.mkdir()
    pd.DataFrame({
        "trade_date": pd.to_datetime(["2023-01-03", "2023-01-31", "2023-03-01"]),
        "equity": [100.0, 110.0, 99.0],
        "benchmark_equity": [200.0, float("nan"), 220.0],
    }).to_parquet(path / "nav.parquet", index=False)
    response = client.get(PREFIX + "/runs/analytics-contract/analytics")
    assert response.status_code == 200, response.text
    output = response.json()
    rows = output["normalized"]["rows"]
    assert [row["equity"] for row in rows] == pytest.approx([1, 1.1, .99])
    assert [row["benchmark_equity"] for row in rows] == [1, None, 1.1]
    assert [row["drawdown"] for row in output["drawdown"]["rows"]] == pytest.approx([0, 0, -.1])
    assert [row["month"] for row in output["monthly"]["rows"]] == ["2023-01", "2023-03"]
    # A missing first benchmark point cannot be rebased to another start date.
    frame = pd.read_parquet(path / "nav.parquet")
    frame.loc[0, "benchmark_equity"] = float("nan")
    frame.to_parquet(path / "nav.parquet", index=False)
    normalized = client.get(PREFIX + "/runs/analytics-contract/analytics").json()["normalized"]
    assert "benchmark_equity" not in normalized["columns"]


def test_legacy_plan_links_survive_migration_and_can_be_reused(tmp_path):
    path = tmp_path / "plans.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE plan_runs (owner TEXT NOT NULL, plan_id TEXT NOT NULL, "
            "revision INTEGER NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(owner, run_id))"
        )
        db.execute("INSERT INTO plan_runs VALUES ('alice', 'legacy', 1, 'historical-run')")
    store = ResearchPlanStore(path)
    assert store.runs("alice", "legacy", 1) == ["historical-run"]
    snapshot = {"execution": {"fee": 0.01}}
    first = store.save("alice", "复用一", snapshot)
    second = store.save("alice", "复用二", snapshot)
    for plan in (first, second):
        store.link_run("alice", plan, "historical-run", snapshot)
        assert store.runs("alice", plan["plan_id"], 1) == ["historical-run"]
    assert ResearchPlanStore(path).runs("alice", "legacy", 1) == ["historical-run"]


def test_patch_request_uses_engine_warmup_and_guided_plan_retains_origin(environment):
    _, _, client, service = environment
    body = client.get(PREFIX + "/backtests/defaults").json()
    patch = client.post(PREFIX + "/backtests/data-request", json=body)
    assert patch.status_code == 200, patch.text
    engine, _ = service.build_engine(service.default_request())
    assert patch.json()["start_date"] == str(
        engine._warmup_start_date(service.default_request().start_date)
    )
    assert set(patch.json()["datasets"]) == {
        "security_master",
        "daily_bars",
        "corporate_actions",
        "benchmark_bars",
    }
    draft = {
        "idea": "低波动",
        "start_date": body["start_date"],
        "end_date": body["end_date"],
        "initial_cash": body["initial_cash"],
        "top_n": 2,
        "rebalance": "weekly",
    }
    prepared = client.post(PREFIX + "/research/ideas/prepare", json=draft).json()
    saved = client.post(
        PREFIX + "/research/plans",
        json={"title": "引导式", "request": prepared, "inputs": {"scope": "guided", **draft}},
    ).json()
    restored = client.get(
        f"{PREFIX}/research/plans/{saved['plan_id']}/{saved['revision']}/request"
    ).json()
    assert restored["inputs"]["scope"] == "guided" and restored["inputs"]["idea"] == "低波动"
    modified = client.post(
        PREFIX + "/research/ideas/prepare",
        json={
            **draft,
            "initial_cash": 2000000,
            "plan_id": saved["plan_id"],
            "plan_revision": saved["revision"],
        },
    )
    assert modified.status_code == 200, modified.text
    assert modified.json()["plan_id"] == saved["plan_id"]
    assert modified.json()["initial_cash"] == 2000000


def test_nl_adapter_validates_model_output_without_executing_code(environment, monkeypatch):
    _, app, client, _ = environment
    template_id = client.get(PREFIX + "/strategies/templates").json()["items"][0]["template_id"]
    definition = client.get(f"{PREFIX}/strategies/templates/{template_id}/balanced").json()[
        "definition"
    ]

    class Client:
        def chat_structured(self, messages, schema, **kwargs):
            assert schema is NLStrategyDraft
            return schema.model_validate(definition), None

    monkeypatch.setattr("quant_platform.api.advanced_tasks.llm", lambda frozen: Client())
    ctx = app.state.context
    ctx.progress = lambda *args: None
    result = execute_advanced(
        "nl_strategy",
        {"description": "价格高于均线时买入", "provider": "mock"},
        ctx,
        {"advanced": {}},
    )
    assert result["definition"]["strategy_id"] == definition["strategy_id"]
    assert result["explanation"]


def test_risk_counts_and_exports_use_full_events_beyond_preview(environment):
    _, _, client, service = environment
    run = service.run().result.run_id
    frame = pd.DataFrame(
        {"trade_date": ["2023-04-28"] * 1101, "decision": ["ADJUST"] * 501 + ["REJECT"] * 600}
    )
    frame.to_parquet(service.runs_root / run / "risk_events.parquet", index=False)
    response = client.get(PREFIX + "/risk/events?limit=1").json()
    assert len(response["rows"]) == 1 and response["total"] >= 1101
    assert response["counts"]["自动调整次数"] >= 501
    assert response["counts"]["拒绝次数"] >= 600
    exported = client.get(PREFIX + "/risk/events/export.csv")
    assert exported.status_code == 200 and len(exported.content.splitlines()) > 1101
