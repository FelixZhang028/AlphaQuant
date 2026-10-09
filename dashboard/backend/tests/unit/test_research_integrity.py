"""Regression checks for truthful runs, effective inputs, and held-out research."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant import run_evidence
from app.routes import backtests, workspace
from app.routes.auth import get_current_user
from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.factor_research_service import FrameFactor, research_combination
from quant_platform.backtest.validity import CURRENT_AUDIT_VERSION
from quant_platform.factors.builtins import _high_distance_20
from quant_platform.risk.config import RiskLimits


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evidence, "RUNTIME_ROOT", tmp_path)
    db = tmp_path / "test.db"
    @contextmanager
    def connect():
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            yield conn
    with connect() as conn:
        conn.execute("CREATE TABLE backtests (id INTEGER PRIMARY KEY, user_id INTEGER, strategy TEXT, market TEXT, from_date TEXT, to_date TEXT, status TEXT, result TEXT, created_at TEXT)")
    monkeypatch.setattr(backtests, "get_conn", connect)
    monkeypatch.setattr(workspace, "get_conn", connect)
    monkeypatch.setattr(workspace, "_cached_grade", lambda *_: None)
    app = FastAPI()
    app.include_router(backtests.router)
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    return TestClient(app), connect, tmp_path


def save_run(api, number, *, user=1, dates=None, equity=None, status="WARNING", reliable=True, issues=None):
    _, connect, root = api
    directory = root / "runs" / str(number)
    directory.mkdir(parents=True)
    dates = dates or ["2025-01-02", "2025-01-03", "2025-01-06"]
    equity = equity if equity is not None else [100, 110, 105]
    pd.DataFrame({"trade_date": pd.to_datetime(dates), "equity": equity}).to_parquet(directory / "nav.parquet")
    summary = {"cumulative_return": .05, "annual_return": .2, "max_drawdown": -5 / 110, "sharpe": 1.234, "sortino": None, "calmar": 4.4}
    (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (directory / "validity_report.json").write_text(json.dumps({"audit_version": CURRENT_AUDIT_VERSION,
        "status": status, "metrics_reliable": reliable, "issues": issues or []}), encoding="utf-8")
    result = {"output_dir": str(directory), "total_return": 5.0, "max_drawdown": round(500 / 110, 2)}
    with connect() as conn:
        conn.execute("INSERT INTO backtests VALUES (?,?,?,?,?,?,?,?,?)", (number, user, f"strategy-{number}", "当前股票池", dates[0], dates[-1], "完成", json.dumps(result), "2025-01-07"))
    return directory


def test_comparison_reads_real_files_and_has_stable_identity(api):
    client, _, _ = api
    save_run(api, 1)
    save_run(api, 2, equity=[200, 180, 210])
    body = {"run_ids": ["run-1", "run-2"]}
    first = client.post("/api/v1/runs/compare", json=body)
    assert first.status_code == 200, first.text
    data = first.json()
    assert data == client.post("/api/v1/runs/compare", json=body).json()
    assert data["source"] == "persisted_backtest"
    assert data["normalized_nav"][0] == {"trade_date": "2025-01-02", "run-1": 1.0, "run-2": 1.0}
    assert data["normalized_nav"][1]["run-2"] == .9
    detail = client.get("/api/v1/backtests/1").json()["result"]
    assert data["comparison"][0]["cumulative_return"] == detail["total_return"]
    assert data["comparison"][0]["max_drawdown"] == detail["max_drawdown"]
    assert data["comparison"][0]["strategy"] == "strategy-1"


@pytest.mark.parametrize("ids, expected", [(["run-1", "run-999"], 404), (["run-1", "run-3"], 404), (["run-1", "run-1"], 400), (["garbage", "run-1"], 400)])
def test_comparison_rejects_unknown_foreign_and_duplicate_ids(api, ids, expected):
    save_run(api, 1)
    save_run(api, 3, user=2)
    assert api[0].post("/api/v1/runs/compare", json={"run_ids": ids}).status_code == expected


@pytest.mark.parametrize("defect", ["missing", "duplicate", "infinite", "disjoint", "bad_summary"])
def test_comparison_never_fabricates_missing_observations(api, defect):
    save_run(api, 1)
    directory = save_run(api, 2,
        dates=["2026-01-02", "2026-01-05", "2026-01-06"] if defect == "disjoint" else None,
        equity=[100, float("inf"), 105] if defect == "infinite" else None)
    if defect == "missing":
        (directory / "nav.parquet").unlink()
    if defect == "duplicate":
        nav = pd.read_parquet(directory / "nav.parquet")
        nav.loc[1, "trade_date"] = nav.loc[0, "trade_date"]
        nav.to_parquet(directory / "nav.parquet")
    if defect == "bad_summary":
        (directory / "summary.json").write_text("[]")
    assert api[0].post("/api/v1/runs/compare", json={"run_ids": ["run-1", "run-2"]}).status_code == 422


def test_warning_and_legacy_labels_match_across_endpoints(api):
    warning = {"code": "UNKNOWN_MARKET_STATUS", "severity": "WARNING", "message": "状态缺口"}
    save_run(api, 1, issues=[warning])
    directory = save_run(api, 2, status="VALID")
    (directory / "validity_report.json").unlink()
    client = api[0]
    detail = client.get("/api/v1/backtests/2").json()["result"]
    assert detail["legacy_unverified"] and not detail["metrics_reliable"]
    comparison = client.post("/api/v1/runs/compare", json={"run_ids": ["run-1", "run-2"]}).json()["comparison"]
    library = {r["run_id"]: r for r in client.get("/api/v1/runs").json()["items"]}
    history = {r["id"]: r["result"] for r in client.get("/api/v1/backtests").json()}
    for r in comparison:
        audited = client.get(f"/api/v1/runs/{r['run_id']}/audit").json()
        for key in ["metrics_reliable", "legacy_unverified", "validity_status", "validity_issues"]:
            assert r[key] == library[r["run_id"]][key] == history[int(r["run_id"][4:])][key]
            if key != "validity_issues":
                assert audited[key] == r[key]
    assert comparison[0]["validity_issues"] == [warning]


def test_corrupt_or_explicitly_invalid_evidence_never_upgrades(api):
    directory = save_run(api, 1, status="VALID")
    invalid = run_evidence.run_evidence({"output_dir": str(directory), "metrics_reliable": False})
    assert not invalid["metrics_reliable"]
    (directory / "validity_report.json").write_text(json.dumps({"audit_version": CURRENT_AUDIT_VERSION, "status": "VALID", "metrics_reliable": True, "issues": ["broken"]}))
    assert not run_evidence.run_evidence({"output_dir": str(directory)})["metrics_reliable"]


def test_form_inputs_reach_execution_and_persist_in_result(api, monkeypatch):
    captured = []
    defaults = BacktestRequest("real", "test", {"lookback": 20}, date(2025, 1, 1), date(2025, 12, 31), 1e6, 10, "weekly")
    metadata = SimpleNamespace(plugin_name="real", display_name="真实策略", defaults=lambda: {"lookback": 99})
    def run(request):
        captured.append(request)
        summary = {"initial_cash": request.initial_cash, "metrics_reliable": True, "validity_status": "VALID"}
        return SimpleNamespace(output_dir=api[2] / "runs" / "spy", result=SimpleNamespace(summary=summary,
            nav=pd.DataFrame({"trade_date": [pd.Timestamp("2025-01-02")], "equity": [request.initial_cash]}),
            fills=pd.DataFrame(), positions=pd.DataFrame(), run_id="spy"))
    service = SimpleNamespace(default_request=lambda: defaults, available_strategies=lambda: [metadata], run=run)
    monkeypatch.setattr(backtests, "build_backtest_service", lambda _: service)
    monkeypatch.setattr(backtests, "local_data_bounds", lambda: (date(2020, 1, 1), date(2026, 1, 1)))
    monkeypatch.setattr(backtests, "user_risk_limits", lambda _: RiskLimits())
    monkeypatch.setattr(backtests, "security_names", lambda: {})
    payload = {"strategy": "real", "market": "当前股票池", "from_date": "2025-01-01", "to_date": "2025-12-31",
        "initial_capital": 250000, "max_positions": 3, "rebalance": "daily"}
    response = api[0].post("/api/v1/backtests", json=payload)
    assert response.status_code == 201, response.text
    assert captured[0].initial_cash == 250000 and captured[0].top_n == 3 and captured[0].rebalance == "daily"
    assert captured[0].risk_limits.max_positions == 3
    result = api[0].get(f"/api/v1/backtests/{response.json()['id']}").json()["result"]
    assert result["equity"] == [250000] and result["effective_config"]["max_positions"] == 3
    for change in [{"strategy": "does-not-exist"}, {"market": "纳指100"}, {"rebalance": "yearly"}, {"initial_capital": -1}, {"max_positions": 0}, {"unused": True}]:
        assert api[0].post("/api/v1/backtests", json={**payload, **change}).status_code == 422
    assert len(captured) == 1
    assert api[0].get("/api/v1/backtests/catalog").json()["items"] == [{"value": "real", "label": "真实策略"}]


@pytest.mark.parametrize("adjustment", [0.5, 2.0, "split"])
def test_high_distance_uses_consistent_adjusted_units(adjustment):
    bars = pd.DataFrame({"trade_date": pd.bdate_range("2025-01-01", periods=30), "symbol": "A", "raw_close": 100., "raw_high": 110.})
    if adjustment == "split":
        bars.loc[15:, ["raw_close", "raw_high"]] /= 2
        bars["adjusted_close"] = 50.
    else:
        bars["adjusted_close"] = bars.raw_close * adjustment
    values = _high_distance_20(bars)
    assert np.allclose(values.value.dropna(), 100 / 110 - 1)


def research_fixture(reverse_test=False):
    dates = pd.bdate_range("2025-01-01", periods=100)
    symbols = [f"S{i}" for i in range(10)]
    rows = []
    for t, day in enumerate(dates):
        for i, symbol in enumerate(symbols):
            exponent = min(t, 59) * (i+1)*.001 + max(t-59, 0) * ((10-i) if reverse_test else (i+1))*.001
            rows.append({"trade_date": day, "symbol": symbol, "adjusted_close": 100*np.exp(exponent)})
    bars = pd.DataFrame(rows)
    class Repository:
        def get_daily_bars(self, symbols=None, end_date=None):
            result = bars[bars.trade_date <= pd.Timestamp(end_date)].copy()
            return result[result.symbol.isin(symbols)] if symbols is not None else result
    def factor(name, scores):
        values = bars[["trade_date", "symbol"]].rename(columns={"trade_date": "date"})
        values["value"] = np.tile(scores, len(dates))
        return FrameFactor(name=name, display_name=name, values=values)
    return Repository(), dates, symbols, (factor("positive", np.arange(10)), factor("second", np.roll(np.arange(10), 1)), factor("negative", -np.arange(10)))


def test_holdout_prices_cannot_change_training_choices():
    results = []
    for reverse in (False, True):
        repository, dates, symbols, factors = research_fixture(reverse)
        result = research_combination(repository, factors[:2], train_start=dates[0].date(), train_end=dates[59].date(),
            test_start=dates[60].date(), test_end=dates[-1].date(), mode="ic", horizon=5, n_groups=5, symbols=symbols, corr_threshold=.95)
        assert result.train_signal_end == dates[53].date() and result.purged_sessions == 6
        results.append(result)
    assert results[0].weights == results[1].weights and results[0].dropped == results[1].dropped
    pd.testing.assert_frame_equal(results[0].correlation, results[1].correlation)
    assert results[0].reports["我的组合"].rank_ic_mean > 0
    assert results[1].reports["我的组合"].rank_ic_mean < 0


def test_negative_ic_is_not_converted_into_positive_weight():
    repository, dates, symbols, factors = research_fixture()
    result = research_combination(repository, (factors[0], factors[2]), train_start=dates[0].date(), train_end=dates[59].date(),
        test_start=dates[60].date(), test_end=dates[-1].date(), mode="ic", horizon=5, n_groups=5, symbols=symbols)
    assert result.weights == {"positive": 1.0, "negative": 0.0}
    from app.quant.result_adapter import factor_report_to_dict
    groups = factor_report_to_dict(result.reports["我的组合"])["group_mean_returns"]
    assert set(groups) == {"G1", "G2", "G3", "G4", "G5"}


def test_unknown_status_warning_and_missing_execution_cannot_grade_a():
    from quant_platform.backtest.credibility import audit_credibility
    from quant_platform.backtest.multiple_testing import SelectionBiasResult
    validity = {"status": "WARNING", "metrics_reliable": True, "issues": [{"code": "UNKNOWN_MARKET_STATUS", "severity": "WARNING", "message": "未知交易状态"}]}
    report = audit_credibility(validity, {}, {}, pd.DataFrame(), pd.DataFrame(), selection_bias=SelectionBiasResult("not_applicable", "一次尝试"))
    assert report.grade != "A"
    assert any(f.severity == "warn" and f.message == "未知交易状态" for d in report.dimensions for f in d.findings)


@pytest.mark.parametrize("code", ["EXTREME_DAILY_RETURN", "MISSING_ADJ_FACTOR", "FIXED_UNIVERSE", "IN_SAMPLE_ONLY"])
def test_every_original_warning_is_preserved_without_double_counting(code):
    from quant_platform.backtest.credibility import audit_credibility
    from quant_platform.backtest.multiple_testing import SelectionBiasResult
    validity = {"status": "WARNING", "metrics_reliable": True, "observations": 250,
        "issues": [{"code": code, "severity": "WARNING", "message": "原始警告"}]}
    execution = {"unknown_status_policy": "reject_trade", "max_participation": .01, "historical_fees": True}
    report = audit_credibility(validity, {}, execution, pd.DataFrame(), pd.DataFrame(), selection_bias=SelectionBiasResult("not_applicable", "一次尝试"))
    assert report.grade == "B"
    assert any(f.severity == "warn" and f.message == "原始警告" for d in report.dimensions for f in d.findings)


def test_short_and_no_trade_samples_are_explicitly_flagged():
    from quant_platform.backtest.credibility import audit_credibility
    from quant_platform.backtest.multiple_testing import SelectionBiasResult
    execution = {"unknown_status_policy": "reject_trade", "max_participation": .01, "historical_fees": True}
    report = audit_credibility({"status": "VALID", "metrics_reliable": True, "observations": 4, "issues": []},
        {"fills": 0}, execution, pd.DataFrame(), pd.DataFrame(), selection_bias=SelectionBiasResult("not_applicable", "一次尝试"))
    assert report.grade == "C"
    codes = {f.code for d in report.dimensions for f in d.findings}
    assert {"SHORT_SAMPLE", "NO_FILLS"}.issubset(codes)


@pytest.mark.parametrize("partitioned", [True, False])
def test_filtered_parquet_read_preserves_date_and_universe_semantics(tmp_path, partitioned):
    from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
    repository = ParquetMarketDataRepository(tmp_path / "market")
    frame = pd.DataFrame({"trade_date": pd.to_datetime(["2024-12-31", "2025-01-02", "2025-01-02 13:00", "2025-01-03"], format="mixed"),
        "symbol": ["A", "A", "B", "A"], "raw_close": [1., 2., 3., 4.]})
    if partitioned:
        repository.save_table("daily_bars", frame)
    else:
        frame.to_parquet(repository.root / "daily_bars.parquet", index=False)
    result = repository.get_daily_bars(symbols=["B"], start_date=date(2025, 1, 2), end_date=date(2025, 1, 2))
    assert result.symbol.tolist() == ["B"] and result.raw_close.tolist() == [3.]
    assert result.trade_date.iloc[0] == pd.Timestamp("2025-01-02")
    assert repository.daily_bar_bounds() == (date(2024, 12, 31), date(2025, 1, 3))
    assert repository.get_daily_bars(symbols=["missing"]).empty


def test_factor_pool_uses_configured_default_instead_of_all_market(monkeypatch):
    monkeypatch.setattr(workspace, "user_universe_symbols", lambda _: [])
    monkeypatch.setattr(workspace, "build_backtest_service", lambda _: SimpleNamespace(configs={"universe": {"universe": {"symbols": ["A", "B"]}}}))
    assert workspace._factor_symbols({"id": 1}) == ["A", "B"]
    monkeypatch.setattr(workspace, "user_universe_symbols", lambda _: ["C"])
    assert workspace._factor_symbols({"id": 1}) == ["C"]
