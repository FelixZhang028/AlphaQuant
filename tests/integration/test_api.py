"""HTTP contracts and parity against real services in an isolated repository."""

import io
import json
from dataclasses import replace
from datetime import date

import pandas as pd
import pytest
import yaml
from fastapi.testclient import TestClient

from quant_platform.api.common import resource_path, wire
from quant_platform.api.main import create_app
from quant_platform.application.backtest_service import BacktestService
from quant_platform.sample_data import generate_sample_market_data

PREFIX = "/api/v1"


@pytest.fixture(scope="module")
def environment(tmp_path_factory):
    root = tmp_path_factory.mktemp("http-api")
    market = root / "market"
    symbols = ["000001.SZ", "000002.SZ", "600000.SH", "600036.SH"]
    generate_sample_market_data(market, symbols, date(2022, 1, 3), date(2023, 12, 29))

    def config(name, value):
        path = root / f"{name}.yaml"
        path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
        return str(path)

    universe = config(
        "universe",
        {
            "universe": {
                "symbols": symbols,
                "filters": {
                    "minimum_listing_days": 61,
                    "minimum_history_days": 61,
                    "minimum_average_amount": 1,
                },
            }
        },
    )
    strategy = config(
        "strategy",
        {
            "strategy": {
                "plugin": "a_share_momentum",
                "id": "api_test",
                "rebalance": "weekly",
                "parameters": {"short_window": 20, "long_window": 60, "minimum_average_amount": 1},
            }
        },
    )
    execution = config(
        "execution",
        {
            "execution": {
                "lot_size": 100,
                "slippage_rate": 0,
                "unknown_status_policy": "reject_trade",
            }
        },
    )
    app_config = config(
        "app",
        {
            "app": {"runtime_dir": str(root / "runtime")},
            "data": {"repository": str(market)},
            "universe": {"config": universe},
            "strategy": {"config": strategy},
            "execution": {"config": execution},
            "portfolio": {"plugin": "equal_weight", "top_n": 2},
            "backtest": {
                "start_date": "2023-01-03",
                "end_date": "2023-04-28",
                "initial_cash": 1_000_000,
                "benchmark": "",
            },
        },
    )
    app = create_app(app_config, prior_path=root / "prior.json")
    with TestClient(app) as client:
        yield root, app, client, BacktestService(app_config)


@pytest.fixture(scope="module")
def completed(environment):
    root, app, client, service = environment
    direct = service.run()
    body = client.get(PREFIX + "/backtests/defaults").json()
    response = client.post(PREFIX + "/backtests/run", json={"request": body, "confirmed": True})
    assert response.status_code == 201, response.text
    return response.json()["run_id"], direct


def test_health_openapi_and_discovery(environment):
    _, app, client, service = environment
    assert client.get(PREFIX + "/health").json()["status"] == "ok"
    spec = client.get("/openapi.json").json()
    assert PREFIX + "/backtests/run" in spec["paths"]
    strategies = client.get(PREFIX + "/strategies").json()["items"]
    assert {item["plugin_name"] for item in strategies} == {
        item.plugin_name for item in service.available_strategies()
    }
    parameter = next(item for item in strategies if item["plugin_name"] == "a_share_momentum")
    assert {p["name"] for p in parameter["parameters"]} >= {"short_window", "long_window"}
    assert client.get(PREFIX + "/readiness").status_code == 200
    assert client.get(PREFIX + "/data/overview").json()["configured_symbol_count"] == 4


def test_real_http_backtest_matches_python_service(environment, completed):
    _, _, client, service = environment
    run_id, direct = completed
    detail = client.get(f"{PREFIX}/runs/{run_id}").json()
    for key in ("cumulative_return", "max_drawdown", "sharpe", "closed_trades"):
        assert detail["summary"][key] == pytest.approx(direct.result.summary[key], abs=1e-12)
    assert detail["validity"] == wire(direct.result.validity)
    actual = client.get(f"{PREFIX}/runs/{run_id}/tables/nav?limit=5000").json()
    assert actual["total"] == len(direct.result.nav)
    assert actual["columns"] == list(direct.result.nav.columns)
    assert [row["equity"] for row in actual["rows"]] == pytest.approx(direct.result.nav.equity)
    audit = client.get(f"{PREFIX}/runs/{run_id}/audit")
    assert audit.status_code == 200, audit.text
    assert len(audit.json()["dimensions"]) == 6
    diagnosis = client.get(f"{PREFIX}/runs/{run_id}/diagnosis")
    assert diagnosis.status_code == 200, diagnosis.text


def test_all_metrics_tables_and_exports_preserve_engine_output(environment, completed):
    """Compare every cell; UUIDs differ between runs but their links must agree."""
    from quant_platform.api.backtests import RunTable
    from quant_platform.api.common import safe_wire

    _, _, client, service = environment
    run_id, direct = completed
    summary = client.get(f"{PREFIX}/runs/{run_id}").json()["summary"]

    def compare(actual, expected):
        if isinstance(expected, dict):
            assert actual.keys() == expected.keys()
            for key in expected:
                compare(actual[key], expected[key])
        elif isinstance(expected, list):
            assert len(actual) == len(expected)
            for left, right in zip(actual, expected):
                compare(left, right)
        elif isinstance(expected, float):
            assert actual == pytest.approx(expected, rel=0, abs=1e-12)
        else:
            assert actual == expected

    expected_summary = safe_wire(direct.result.summary)
    assert summary.get("legacy_unverified") is False
    compare({key: summary[key] for key in expected_summary}, expected_summary)
    identifiers = {}
    for name in RunTable:
        response = client.get(f"{PREFIX}/runs/{run_id}/tables/{name}?limit=5000")
        assert response.status_code == 200, response.text
        actual = response.json()
        persisted = pd.read_parquet(service.runs_root / run_id / f"{name}.parquet")
        compare(actual["rows"], safe_wire(persisted)["rows"])
        expected_frame = pd.read_parquet(service.runs_root / direct.result.run_id / f"{name}.parquet")
        expected = safe_wire(expected_frame)
        assert actual["columns"] == expected["columns"]
        assert actual["total"] == expected["total"]
        # Establish a single bijection across orders, fills and closed trades.
        for left, right in zip(actual["rows"], expected["rows"]):
            for column in actual["columns"]:
                if column in {"filled_at", "generated_at"}:
                    # Wall clock execution time is not a historical trade date.
                    assert pd.Timestamp(left[column]).tzinfo is not None
                    assert pd.Timestamp(right[column]).tzinfo is not None
                    left[column] = right[column]
                if column in {"order_id", "fill_id", "buy_order_id", "sell_order_id"}:
                    namespace = "order_id" if column.endswith("order_id") else "fill_id"
                    key = (namespace, left[column])
                    if key in identifiers:
                        assert identifiers[key] == (namespace, right[column])
                    else:
                        assert (namespace, right[column]) not in identifiers.values()
                        identifiers[key] = (namespace, right[column])
                        # Keep the value separate from the namespace for comparison.
                    left[column] = identifiers[key][1]
        compare(actual["rows"], expected["rows"])
        export = client.get(f"{PREFIX}/runs/{run_id}/tables/{name}/export.csv")
        assert export.status_code == 200 and export.content.startswith(b"\xef\xbb\xbf")
        if not actual["columns"]:
            assert not export.content.decode("utf-8-sig").strip()
            continue
        exported = pd.read_csv(io.BytesIO(export.content), dtype=str, keep_default_na=False)
        persisted = pd.read_parquet(service.runs_root / run_id / f"{name}.parquet")
        expected_csv = pd.read_csv(io.StringIO(persisted.to_csv(index=False)), dtype=str, keep_default_na=False)
        pd.testing.assert_frame_equal(exported, expected_csv)


def test_history_and_snapshot_restore(environment, completed):
    _, _, client, service = environment
    run_id, direct = completed
    records = client.get(PREFIX + "/runs?q=" + run_id).json()
    assert records["total"] == 1
    assert "single" in records["run_kinds"]
    assert client.get(PREFIX + "/runs?q=no-matching-run").json()["run_kinds"] == records["run_kinds"]
    assert "path" not in records["items"][0]
    restored = client.get(f"{PREFIX}/runs/{run_id}/request").json()
    assert restored["baseline_run_id"] == run_id
    assert restored["request"]["snapshot_run_id"] == run_id
    # A restored request continues using its original execution assumptions.
    service.configs["execution"]["execution"]["slippage_rate"] = 0.9
    from quant_platform.api.backtests import build_request
    from quant_platform.api.schemas import BacktestInput

    restored_request = build_request(service, BacktestInput(**restored["request"]))
    assert service.configs["execution"]["execution"]["slippage_rate"] == 0
    assert restored_request.baseline_run_id == run_id
    service.configs = service._load_component_configs()
    compared = client.post(
        PREFIX + "/runs/compare", json={"run_ids": [run_id, direct.result.run_id]}
    )
    assert compared.status_code == 200, compared.text
    assert compared.json()["metrics"]["total"] == 2


def test_filters_pagination_and_full_csv(environment, completed):
    _, _, client, service = environment
    run_id, _ = completed
    query = "?symbols=000001.SZ&start_date=2023-01-03&end_date=2023-04-28"
    preview = client.get(PREFIX + "/data/tables/daily_bars" + query + "&limit=3&offset=1").json()
    assert len(preview["rows"]) == 3 and preview["total"] > 3
    response = client.get(PREFIX + "/data/tables/daily_bars/export.csv" + query)
    assert response.content.startswith(b"\xef\xbb\xbf")
    exported = pd.read_csv(io.BytesIO(response.content))
    assert len(exported) == preview["total"]
    assert set(exported.symbol) == {"000001.SZ"}
    export_nav = client.get(f"{PREFIX}/runs/{run_id}/tables/nav/export.csv")
    expected = pd.read_parquet(service.runs_root / run_id / "nav.parquet")
    actual = pd.read_csv(io.BytesIO(export_nav.content))
    assert len(actual) == len(expected)
    assert actual.equity.tolist() == pytest.approx(expected.equity)


@pytest.mark.parametrize(
    "change",
    [
        {"top_n": 0},
        {"top_n": 1.5},
        {"initial_cash": -1},
        {"start_date": "2025-01-01"},
        {"rebalance": "hourly"},
        {"strategy_parameters": {"does_not_exist": 1}},
        {"strategy_plugin": "not_a_strategy"},
        {"risk_limits": {"max_drawdown": 2}},
        {"unexpected": 1},
    ],
)
def test_invalid_requests_do_not_create_runs(environment, change):
    _, _, client, service = environment
    before = len(service.run_store.list_records())
    body = client.get(PREFIX + "/backtests/defaults").json()
    body.update(change)
    response = client.post(PREFIX + "/backtests/run", json={"request": body, "confirmed": True})
    assert response.status_code == 422, response.text
    assert len(service.run_store.list_records()) == before


def test_confirmation_and_execution_time_data_check(environment):
    _, _, client, service = environment
    body = client.get(PREFIX + "/backtests/defaults").json()
    before = len(service.run_store.list_records())
    assert client.post(PREFIX + "/backtests/run", json={"request": body}).status_code == 409
    body.update(start_date="2070-01-01", end_date="2070-02-01")
    checked = client.post(PREFIX + "/backtests/inspect", json=body)
    assert checked.status_code == 200 and not checked.json()["ready"]
    rejected = client.post(PREFIX + "/backtests/run", json={"request": body, "confirmed": True})
    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "data_not_ready"
    assert len(service.run_store.list_records()) == before


def test_resource_allowlists_and_legacy_missing_files(environment, completed):
    _, _, client, service = environment
    run_id, _ = completed
    assert client.get(PREFIX + "/runs/no-such-run").status_code == 404
    assert client.get(f"{PREFIX}/runs/{run_id}/tables/config.snapshot.yaml").status_code == 422
    assert client.get(PREFIX + "/data/tables/credentials").status_code == 422
    with pytest.raises(Exception) as exc:
        resource_path(service.runs_root, "../outside")
    assert exc.value.code == "invalid_id"
    legacy = service.runs_root / "legacy-test"
    legacy.mkdir(exist_ok=True)
    (legacy / "summary.json").write_text('{"cumulative_return": 0.1}', encoding="utf-8")
    detail = client.get(PREFIX + "/runs/legacy-test")
    assert detail.status_code == 200
    assert detail.json()["summary"]["legacy_unverified"] is True
    assert client.get(PREFIX + "/runs/legacy-test/tables/closed_trades").status_code == 404
    response = client.post(
        PREFIX + "/experiments/optimization/run",
        json={"baseline_run_id": "legacy-test", "parameter_grid": {"short_window": [20]}},
    )
    assert response.status_code == 409


def test_visual_templates_versions_and_copy(environment):
    _, _, client, _ = environment
    templates = client.get(PREFIX + "/strategies/templates").json()["items"]
    assert len(templates) == 6
    template_id = templates[0]["template_id"]
    package = client.get(f"{PREFIX}/strategies/templates/{template_id}/balanced").json()
    body = {key: package[key] for key in ("definition", "top_n", "rebalance")}
    assert client.post(PREFIX + "/strategies/packages/validate", json=body).status_code == 200
    original = client.post(PREFIX + "/strategies/packages", json=body)
    assert original.status_code == 201, original.text
    package_id = original.json()["package_id"]
    revision = client.post(
        PREFIX + "/strategies/packages", json={**body, "revision_of": package_id}
    )
    assert revision.status_code == 201 and revision.json()["package_id"] != package_id
    copied = client.post(f"{PREFIX}/strategies/packages/{package_id}/copy", json={"name": "副本"})
    assert copied.status_code == 201 and copied.json()["source"] == "copy:" + package_id
    prepared = client.post(PREFIX + "/strategies/packages/prepare", json={"package": package})
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["request"]["strategy_plugin"] == "rule_builder"
    assert client.get(f"{PREFIX}/strategies/packages/{package_id}").json() == original.json()


def test_knowledge_write_lock_and_fresh_configuration(environment):
    root, app, client, service = environment
    with app.state.context.mutation():
        assert client.post(PREFIX + "/knowledge", json={"content": "blocked"}).status_code == 409
        assert client.get(PREFIX + "/health").status_code == 200
    added = client.post(
        PREFIX + "/knowledge", json={"content": "不要使用未来数据", "source": "测试"}
    )
    assert added.status_code == 201
    assert client.get(PREFIX + "/knowledge?q=未来").json()["total"] == 1
    entry_id = added.json()["id"]
    assert client.delete(f"{PREFIX}/knowledge/{entry_id}").status_code == 204
    assert client.delete(f"{PREFIX}/knowledge/{entry_id}").status_code == 404
    original = client.get(PREFIX + "/universe").json()["settings"]["symbols"]
    added = client.post(PREFIX + "/universe/symbols", json={"symbols": ["000003"]})
    assert added.status_code == 200, added.text
    assert "000003.SZ" in added.json()["symbols"]
    assert client.get(PREFIX + "/data/overview").json()["configured_symbol_count"] == 5
    removed = client.post(PREFIX + "/universe/symbols/remove", json={"symbols": ["000003"]})
    assert removed.json()["symbols"] == original


def test_optimization_is_real_and_downloadable(environment, completed):
    _, _, client, service = environment
    run_id, _ = completed
    response = client.post(
        PREFIX + "/experiments/optimization/run",
        json={"baseline_run_id": run_id, "parameter_grid": {"short_window": [15, 20]}},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["experiments"]["total"] == 2
    assert {row["status"] for row in result["experiments"]["rows"]} == {"SUCCESS"}
    path = PREFIX + "/experiments/optimization/" + result["optimization_id"]
    assert client.get(path).json()["results"]["total"] == 2
    exported = pd.read_csv(io.BytesIO(client.get(path + "/export.csv").content))
    assert len(exported) == 2
    report = client.get(path).json()
    assert len(report["selection_bias"]) == 2
    assert all(item["trial_count"] == 2 for item in report["selection_bias"])
    assert any(row["dsr"] is not None for row in report["results"]["rows"])
    nav = service.runs_root / result["experiments"]["rows"][0]["run_id"] / "nav.parquet"
    original = nav.read_bytes()
    try:
        nav.unlink()
        changed = client.get(path).json()
        assert all(row["dsr"] is None for row in changed["results"]["rows"])
        assert all(item["status"] == "unavailable" for item in changed["selection_bias"])
        assert [row["rank"] for row in changed["results"]["rows"]] == [row["rank"] for row in report["results"]["rows"]]
        assert [row["sharpe"] for row in changed["results"]["rows"]] == [row["sharpe"] for row in report["results"]["rows"]]
        assert pd.read_csv(io.BytesIO(client.get(path + "/export.csv").content)).dsr.isna().all()
    finally:
        nav.write_bytes(original)


def test_factor_report_keeps_all_sections_and_series_index(environment):
    _, _, client, _ = environment
    assert client.get(PREFIX + "/factors?q=momentum_20").json()["total"] >= 1
    response = client.post(
        PREFIX + "/factors/evaluate",
        json={
            "factor_name": "momentum_20",
            "start_date": "2023-01-03",
            "end_date": "2023-04-28",
            "n_groups": 5,
        },
    )
    assert response.status_code == 200, response.text
    report = response.json()
    assert {"daily_ic", "significance", "annual", "decay", "turnover", "notes"} <= report.keys()
    assert {"index", "values"} == report["group_mean_returns"].keys()
    json.dumps(report, allow_nan=False)


def test_local_origin_policy_and_validation_redaction(environment):
    _, _, client, _ = environment
    assert (
        client.get(PREFIX + "/health", headers={"Origin": "https://untrusted.example"}).status_code
        == 403
    )
    response = client.options(
        PREFIX + "/knowledge",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    rejected = client.post(PREFIX + "/knowledge", json={"content": "ok", "api_key": "test-secret"})
    assert rejected.status_code == 422 and "test-secret" not in rejected.text
    assert client.get(PREFIX + "/health", headers={"host": "untrusted.example"}).status_code == 400


def test_json_missing_values_are_not_zero():
    import numpy as np

    frame = pd.DataFrame(
        {
            "date": [pd.Timestamp("2023-01-01"), pd.NaT],
            "value": [float("nan"), np.inf],
            "code": ["000001.SZ", None],
        }
    )
    result = wire(frame)
    assert result["rows"][0]["value"] is None
    assert result["rows"][1]["date"] is None
    assert wire({"missing": pd.NA, "float": np.float64(np.nan)}) == {"missing": None, "float": None}
    json.dumps(result, allow_nan=False)


def test_walk_forward_uses_real_service_and_persists_windows(environment, completed):
    _, _, client, _ = environment
    run_id, _ = completed
    response = client.post(
        PREFIX + "/experiments/walk-forward/run",
        json={
            "baseline_run_id": run_id,
            "parameter_grid": {"short_window": [20]},
            "start_date": "2022-07-01",
            "end_date": "2023-12-29",
            "training_months": 3,
            "test_months": 1,
            "step_months": 1,
            "max_windows": 2,
        },
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["windows"]["total"] == 2
    assert {row["status"] for row in result["windows"]["rows"]} == {"SUCCESS"}
    path = PREFIX + "/experiments/walk-forward/" + result["validation_id"]
    assert client.get(path).json()["summary"] == result["summary"]
    assert len(pd.read_csv(io.BytesIO(client.get(path + "/export.csv").content))) == 2


def test_update_flags_partial_failure_and_backfill_conflict(environment, monkeypatch):
    from quant_platform.application.data_jobs import DataJobs
    from quant_platform.application.data_service import DataCenterService, DataUpdateResult

    _, _, client, _ = environment
    calls = []

    def update(service, start, end, **kwargs):
        calls.append(kwargs)
        return [
            DataUpdateResult("daily_bars", "v1", "SUCCESS", 10, "完成"),
            DataUpdateResult(
                "benchmark_bars", "v2", "FAILED", 0, "失败", error="token=test-secret"
            ),
        ]

    monkeypatch.setattr(DataCenterService, "update_all", update)
    monkeypatch.setattr(DataJobs, "active", lambda self: None)
    body = {
        "start_date": "2023-01-03",
        "end_date": "2023-04-28",
        "datasets": ["daily_bars", "benchmark_bars"],
        "market_source_order": ["baostock"],
        "allow_market_fallback": False,
        "benchmark_symbols": ["000300.SH", "000905.SH"],
    }
    response = client.post(PREFIX + "/data/update", json=body)
    assert response.status_code == 200, response.text
    assert [row["status"] for row in response.json()["results"]] == ["SUCCESS", "FAILED"]
    assert "test-secret" not in response.text
    assert calls[0]["include_security_master"] is False
    assert calls[0]["include_corporate_actions"] is False
    assert calls[0]["market_source_order"] == ["baostock"]
    assert calls[0]["allow_market_fallback"] is False
    assert calls[0]["benchmark_symbols"] == ["000300.SH", "000905.SH"]
    monkeypatch.setattr(DataJobs, "active", lambda self: {"id": "running"})
    response = client.post(PREFIX + "/data/update", json=body)
    assert response.status_code == 409 and len(calls) == 1


def test_grid_limits_and_guided_risk_constraints(environment, completed, monkeypatch):
    root, app, client, service = environment
    run_id, _ = completed
    response = client.post(
        PREFIX + "/experiments/optimization/run",
        json={"baseline_run_id": run_id, "parameter_grid": {"short_window": list(range(101))}},
    )
    assert response.status_code == 422
    request = {
        "idea": "趋势上涨",
        "start_date": "2023-01-03",
        "end_date": "2023-04-28",
        "initial_cash": 100000,
        "top_n": 3,
        "rebalance": "weekly",
    }
    assert client.post(PREFIX + "/research/ideas/prepare", json=request).status_code == 200
    from quant_platform.risk.config import RiskLimits

    original_default = BacktestService.default_request
    monkeypatch.setattr(
        BacktestService,
        "default_request",
        lambda self: replace(original_default(self), risk_limits=RiskLimits(max_single_weight=0.2)),
    )
    response = client.post(PREFIX + "/research/ideas/prepare", json=request)
    assert (
        response.status_code == 409
        and response.json()["error"]["code"] == "allocation_incompatible"
    )


def test_nonlocal_clients_are_rejected(environment):
    import asyncio

    import httpx

    _, app, _, _ = environment

    async def request():
        transport = httpx.ASGITransport(app=app, client=("192.168.1.5", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
            return await client.get(PREFIX + "/health")

    assert asyncio.run(request()).status_code == 403
