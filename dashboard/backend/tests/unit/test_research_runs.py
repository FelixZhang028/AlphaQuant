"""Parameter search and walk-forward requests reach the real services and report real units."""
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant import research_runs
from app.quant.research_runs import (
    MAX_COMBINATIONS,
    ResearchInputError,
    parameter_grid,
    run_optimization,
    run_walk_forward,
    tunable_parameters,
    walk_forward_range,
)
from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.optimization_service import (
    OptimizationRequest,
    OptimizationService,
    apply_candidate,
)
from quant_platform.application.walk_forward_service import WalkForwardRequest, WalkForwardService
from quant_platform.risk.config import RiskLimits
from quant_platform.strategies.spec import ParameterKind, StrategyMetadata, StrategyParameter

METADATA = StrategyMetadata(
    plugin_name="demo", display_name="演示", description="", required_fields=frozenset(),
    parameters=(
        StrategyParameter("short_window", "短期窗口", ParameterKind.INTEGER, 20, minimum=2, maximum=250),
        StrategyParameter("threshold", "阈值", ParameterKind.NUMBER, 0.0),
        StrategyParameter("definition_json", "规则", ParameterKind.STRING, "{}"),
        StrategyParameter("mode", "模式", ParameterKind.STRING, "a", choices=("a", "b")),
    ),
)
BASE = BacktestRequest(strategy_plugin="demo", strategy_id="demo_1", strategy_parameters=METADATA.defaults(),
                       start_date=date(2025, 1, 1), end_date=date(2025, 12, 31), initial_cash=1e6, top_n=10,
                       rebalance="weekly")


def test_strategy_parameters_come_first_then_the_two_settings_every_strategy_shares():
    offered = tunable_parameters(METADATA, {"short_window": 30}, top_n=5, rebalance="monthly")
    assert [p["name"] for p in offered] == ["short_window", "threshold", "mode", "top_n", "rebalance"]
    assert offered[0]["current"] == 30 and offered[0]["minimum"] == 2 and offered[1]["current"] == 0.0
    holding, frequency = offered[3], offered[4]
    assert (holding["label"], holding["current"], holding["minimum"], holding["maximum"]) == ("持股数量", 5, 1, 500)
    assert frequency["current"] == "monthly" and frequency["choices"] == ["daily", "weekly", "monthly"]
    assert frequency["choice_labels"] == {"daily": "每日", "weekly": "每周", "monthly": "每月"}
    # A rule strategy has no numeric parameters of its own, but can still vary these two.
    rules = replace(METADATA, plugin_name="rule_builder", parameters=METADATA.parameters[2:3])
    assert [(p["name"], p["maximum"]) for p in tunable_parameters(rules, {})] == [("top_n", 50), ("rebalance", None)]


def test_grid_is_validated_against_the_strategy_before_anything_runs():
    assert parameter_grid(METADATA, {"short_window": ["10", 20, 20.0], "mode": ["b"]}) == {
        "short_window": (10, 20), "mode": ("b",)}
    for raw, fragment in [({"window": [1]}, "没有名为 window"), ({"short_window": [1]}, "允许范围 2 ~ 250"),
                          ({"definition_json": ["{}"]}, "没有名为"), ({"short_window": []}, "至少为一个参数"),
                          ({"mode": ["c"]}, "无效"),
                          ({"short_window": list(range(2, 2 + MAX_COMBINATIONS + 1))}, "超过上限")]:
        with pytest.raises(ResearchInputError, match=fragment):
            parameter_grid(METADATA, raw)
    rules = replace(METADATA, plugin_name="rule_builder", parameters=METADATA.parameters[2:3])
    assert parameter_grid(rules, {"top_n": ["3", 5], "rebalance": ["weekly", "monthly"]}) == {
        "top_n": (3, 5), "rebalance": ("weekly", "monthly")}
    with pytest.raises(ResearchInputError, match="可选 daily / weekly / monthly"):
        parameter_grid(rules, {"rebalance": ["yearly"]})
    with pytest.raises(ResearchInputError, match="允许范围 1 ~ 50"):
        parameter_grid(rules, {"top_n": [51]})


def test_a_candidate_changes_request_settings_without_touching_strategy_parameters():
    base = replace(BASE, risk_limits=RiskLimits(max_positions=10))
    changed = apply_candidate(base, {"top_n": 3, "rebalance": "monthly", "short_window": 5})
    assert (changed.top_n, changed.rebalance, changed.risk_limits.max_positions) == (3, "monthly", 3)
    assert changed.strategy_parameters == {**BASE.strategy_parameters, "short_window": 5}
    assert (base.top_n, base.rebalance, base.strategy_parameters["short_window"]) == (10, "weekly", 20)
    # A strategy that defines its own parameter with the same name keeps it.
    own = replace(BASE, strategy_parameters={"top_n": 7})
    assert apply_candidate(own, {"top_n": 3}).strategy_parameters == {"top_n": 3}
    assert apply_candidate(own, {"top_n": 3}).top_n == 10


class RecordingBacktests:
    """Stands in for BacktestService: records each request and scores it by holding count."""

    app_config_path = "unused"
    configs: dict = {}

    def __init__(self, root):
        self.runs_root = root / "runs"
        self.requests = []

    def run(self, request):
        self.requests.append(request)
        summary = {"sharpe": 1.0 + request.top_n / 10 + (0.5 if request.rebalance == "monthly" else 0.0),
                   "max_drawdown": -0.1, "cumulative_return": 0.1, "metrics_reliable": True}
        return SimpleNamespace(result=SimpleNamespace(run_id=f"run-{len(self.requests)}", summary=summary))


def test_the_real_search_services_vary_holding_count_and_rebalance_frequency(tmp_path):
    backtests = RecordingBacktests(tmp_path)
    grid = {"top_n": (3, 5), "rebalance": ("weekly", "monthly")}
    result = OptimizationService(backtests).run(OptimizationRequest(base_request=BASE, parameter_grid=grid))
    assert sorted((r.top_n, r.rebalance, r.risk_limits.max_positions) for r in backtests.requests) == [
        (3, "monthly", 3), (3, "weekly", 3), (5, "monthly", 5), (5, "weekly", 5)]
    assert all(r.strategy_parameters == BASE.strategy_parameters for r in backtests.requests)
    best = result.experiments.iloc[0]
    assert (int(best["param_top_n"]), best["param_rebalance"]) == (5, "monthly")

    walker = RecordingBacktests(tmp_path / "walk")
    walked = WalkForwardService(walker).run(WalkForwardRequest(
        base_request=replace(BASE, start_date=date(2024, 1, 1), end_date=date(2025, 3, 31)),
        parameter_grid=grid, training_months=12, test_months=3, step_months=3, max_windows=1))
    tested = walker.requests[-1]
    # The unseen test window runs with the winner of the training window, including request settings.
    assert (tested.run_kind, tested.top_n, tested.rebalance, tested.risk_limits.max_positions) == (
        "walk_forward_oos", 5, "monthly", 5)
    assert '"top_n": 5' in walked.windows.iloc[0]["selected_parameters"]
    assert '"rebalance": "monthly"' in walked.windows.iloc[0]["selected_parameters"]


def test_walk_forward_uses_the_latest_data_that_fits_the_windows():
    bounds = (date(2015, 1, 5), date(2026, 10, 9))
    assert walk_forward_range(bounds, training_months=12, test_months=3, step_months=3, max_windows=4) == (
        date(2024, 10, 10), date(2026, 10, 9))
    assert walk_forward_range(bounds, training_months=60, test_months=24, step_months=24, max_windows=24)[0] == date(2015, 1, 5)


def test_optimization_reports_percentages_failures_and_selection_bias(monkeypatch):
    seen = {}

    class FakeOptimizer:
        def __init__(self, service):
            seen["service"] = service

        def run(self, request):
            seen["request"] = request
            return SimpleNamespace(optimization_id="opt-1", experiments=pd.DataFrame([
                {"param_short_window": 10, "param_threshold": 0.0, "status": "SUCCESS", "run_id": "r1", "error": None,
                 "eligible": True, "rank": 1, "objective_value": 1.2345678, "cumulative_return": 0.2231,
                 "annual_return": 0.25, "max_drawdown": -0.0755, "sharpe": 1.2345678, "dsr": 0.94123,
                 "selection_bias_status": "警告", "selection_bias_reason": "来自 2 次尝试"},
                {"param_short_window": 20, "param_threshold": 0.0, "status": "FAILED", "run_id": None,
                 "error": "ValueError: 参数无效", "eligible": False, "rank": pd.NA, "objective_value": float("nan"),
                 "cumulative_return": float("nan"), "annual_return": float("nan"), "max_drawdown": float("nan"),
                 "sharpe": float("nan"), "dsr": None, "selection_bias_status": "无法评估", "selection_bias_reason": None},
            ]).astype({"rank": "Int64"}))

    monkeypatch.setattr(research_runs, "OptimizationService", FakeOptimizer)
    result = run_optimization("service", BASE, {"short_window": (10, 20)}, objective="sharpe",
                              max_drawdown_limit=0, baseline_run_id="base-run")
    assert seen["service"] == "service" and seen["request"].base_request is BASE
    assert seen["request"].max_drawdown_limit is None and seen["request"].baseline_run_id == "base-run"
    best, failed = result["results"]
    assert best == {"rank": 1, "eligible": True, "status": "SUCCESS", "error": None, "run_id": "r1",
                    "parameters": {"short_window": 10}, "objective_value": 1.2346, "cumulative_return": 22.31,
                    "annual_return": 25.0, "max_drawdown": 7.55, "sharpe": 1.23, "dsr": 0.9412,
                    "selection_bias_status": "警告", "selection_bias_reason": "来自 2 次尝试"}
    assert failed["rank"] is None and failed["sharpe"] is None and failed["error"] == "参数无效"
    assert result["selection_bias"] == {"status": "警告", "message": "来自 2 次尝试", "dsr": 0.9412}
    assert (result["combination_count"], result["start_date"], result["end_date"]) == (2, "2025-01-01", "2025-12-31")
    with pytest.raises(ResearchInputError):
        run_optimization("service", BASE, {"short_window": (10,)}, objective="profit", max_drawdown_limit=0.3,
                         baseline_run_id="base-run")


def test_walk_forward_refuses_oversized_jobs_and_reports_each_window(monkeypatch):
    class FakeWalker:
        windows = 4
        ran = 0

        def __init__(self, service):
            pass

        def build_windows(self, request):
            return tuple(range(self.windows))

        def run(self, request):
            FakeWalker.ran += 1
            return SimpleNamespace(validation_id="wf-1", windows=pd.DataFrame([
                {"window": 1, "train_start": date(2024, 10, 10), "train_end": date(2025, 10, 9),
                 "test_start": date(2025, 10, 10), "test_end": date(2026, 1, 9), "status": "SUCCESS", "error": None,
                 "train_run_id": "t1", "test_run_id": "o1",
                 "selected_parameters": '{"short_window": 10, "threshold": 0.0}', "train_objective_value": 1.5,
                 "test_cumulative_return": 0.0928, "test_max_drawdown": -0.0447, "test_sharpe": 2.341},
                {"window": 2, "train_start": date(2025, 1, 10), "train_end": date(2026, 1, 9),
                 "test_start": date(2026, 1, 10), "test_end": date(2026, 4, 9), "status": "FAILED",
                 "error": "ValueError: 训练期没有找到满足约束的参数"},
            ]), summary={"successful_windows": 1, "failed_windows": 1, "out_of_sample_cumulative_return": 0.0928,
                         "average_window_return": 0.0928, "positive_window_ratio": 1.0,
                         "worst_window_drawdown": -0.0447, "average_window_sharpe": 2.341, "trust_warning": "提示"})

    monkeypatch.setattr(research_runs, "WalkForwardService", FakeWalker)
    options = dict(objective="sharpe", training_months=12, test_months=3, step_months=3, max_windows=4,
                   baseline_run_id="base-run")
    result = run_walk_forward("service", BASE, {"short_window": (10, 20)}, **options)
    assert result["backtest_count"] == 12 and result["window_count"] == 2
    assert result["windows"][0] == {
        "window": 1, "status": "SUCCESS", "error": None, "train_start": "2024-10-10", "train_end": "2025-10-09",
        "test_start": "2025-10-10", "test_end": "2026-01-09", "train_run_id": "t1", "test_run_id": "o1",
        "selected_parameters": {"short_window": 10}, "train_objective_value": 1.5, "test_cumulative_return": 9.28,
        "test_max_drawdown": 4.47, "test_sharpe": 2.34}
    assert result["windows"][1]["selected_parameters"] == {} and result["windows"][1]["test_sharpe"] is None
    # Engine codes and exception class names are not shown to the user.
    assert result["windows"][1]["error"] == "训练期没有找到满足约束的参数"
    assert research_runs._reason("BacktestValidityError: MISSING_CORPORATE_ACTION: 000001.SZ 复权因子变化") == "000001.SZ 复权因子变化"
    assert result["summary"]["positive_window_ratio"] == 100.0 and result["summary"]["worst_window_drawdown"] == 4.47
    FakeWalker.windows = 40
    with pytest.raises(ResearchInputError, match="需要运行 120 次回测"):
        run_walk_forward("service", BASE, {"short_window": (10, 20)}, **options)
    assert FakeWalker.ran == 1


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 7}
    monkeypatch.setattr(workspace, "_research_baseline", lambda ref, user: ("service", BASE, METADATA, "engine-run"))
    with TestClient(app) as test_client:
        yield test_client


def test_routes_pass_validated_grids_to_the_real_runners(client, monkeypatch):
    calls = {}

    def fake_optimize(service, base, grid, **options):
        calls["optimize"] = (service, base, grid, options)
        return {"results": []}

    def fake_walk(service, base, grid, **options):
        calls["walk"] = (base, grid, options)
        return {"windows": []}

    monkeypatch.setattr(workspace, "run_optimization", fake_optimize)
    monkeypatch.setattr(workspace, "run_walk_forward", fake_walk)
    monkeypatch.setattr(workspace, "local_data_bounds", lambda: (date(2015, 1, 5), date(2026, 10, 9)))
    body = {"baseline_run_id": "run-3", "parameter_grid": {"short_window": [10, 20]}, "max_drawdown_limit": 0.2}
    assert client.post("/api/v1/research/optimize", json=body).json() == {"results": []}
    assert calls["optimize"] == ("service", BASE, {"short_window": (10, 20)},
                                 {"objective": "sharpe", "max_drawdown_limit": 0.2, "baseline_run_id": "engine-run"})
    assert client.post("/api/v1/research/walk-forward", json={**body, "max_windows": 4}).status_code == 200
    walked_base, _, options = calls["walk"]
    # The baseline's own dates are replaced by the latest local data that fits the windows.
    assert (walked_base.start_date, walked_base.end_date) == (date(2024, 10, 10), date(2026, 10, 9))
    assert options["max_windows"] == 4 and options["baseline_run_id"] == "engine-run"


def test_routes_explain_bad_grids_and_engine_failures_instead_of_inventing_results(client, monkeypatch):
    bad = client.post("/api/v1/research/optimize", json={"baseline_run_id": "run-3", "parameter_grid": {"window": [1]}})
    assert bad.status_code == 422 and "没有名为 window" in bad.json()["detail"]

    def explode(*args, **kwargs):
        raise RuntimeError("engine down")

    monkeypatch.setattr(workspace, "run_optimization", explode)
    failed = client.post("/api/v1/research/optimize",
                         json={"baseline_run_id": "run-3", "parameter_grid": {"short_window": [10]}})
    assert failed.status_code == 422 and failed.json()["detail"].startswith("参数优化失败")
    overlap = client.post("/api/v1/research/walk-forward", json={
        "baseline_run_id": "run-3", "parameter_grid": {"short_window": [10]}, "test_months": 6, "step_months": 3})
    assert overlap.status_code == 400
