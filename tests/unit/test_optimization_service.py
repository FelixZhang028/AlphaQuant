from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.optimization_service import (
    OptimizationRequest,
    OptimizationService,
)


class _FakeBacktests:
    def __init__(self, root: Path, request: BacktestRequest) -> None:
        self.runs_root = root / "runs"
        self.request = request
        self.calls: list[BacktestRequest] = []

    def run(self, request: BacktestRequest) -> SimpleNamespace:
        self.calls.append(request)
        value = int(request.strategy_parameters["lookback"])
        summary = {
            "sharpe": value / 10.0,
            "annual_return": value / 100.0,
            "max_drawdown": -value / 100.0,
            "metrics_reliable": True,
        }
        result = SimpleNamespace(run_id=f"run-{value}", summary=summary)
        return SimpleNamespace(result=result)


def test_grid_optimization_ranks_eligible_results(tmp_path: Path) -> None:
    base = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="fake",
        strategy_parameters={"lookback": 10},
        start_date=__import__("datetime").date(2024, 1, 1),
        end_date=__import__("datetime").date(2024, 12, 31),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )
    service = OptimizationService(_FakeBacktests(tmp_path, base))  # type: ignore[arg-type]
    request = OptimizationRequest(
        base_request=replace(base),
        parameter_grid={"lookback": (10, 20, 40)},
        objective="sharpe",
        max_drawdown_limit=0.25,
        baseline_run_id="baseline-1",
    )

    result = service.run(request)

    assert result.experiments.iloc[0]["param_lookback"] == 20
    assert result.experiments.iloc[0]["rank"] == 1
    assert result.experiments["eligible"].tolist() == [True, True, False]
    assert (result.output_dir / "results.csv").exists()
    assert all(call.run_kind == "optimization" for call in service.backtests.calls)
    assert all(call.baseline_run_id == "baseline-1" for call in service.backtests.calls)
    request_json = json.loads((result.output_dir / "request.json").read_text(encoding="utf-8"))
    assert request_json["baseline_run_id"] == "baseline-1"


def test_grid_optimization_excludes_unreliable_results() -> None:
    frame = pd.DataFrame(
        {
            "status": ["SUCCESS", "SUCCESS"],
            "sharpe": [3.0, 1.0],
            "max_drawdown": [-0.10, -0.10],
            "metrics_reliable": [False, True],
        }
    )
    base = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="fake",
        strategy_parameters={"lookback": 10},
        start_date=__import__("datetime").date(2024, 1, 1),
        end_date=__import__("datetime").date(2024, 12, 31),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )
    request = OptimizationRequest(base_request=base, parameter_grid={"lookback": (10,)})

    ranked = OptimizationService._rank(frame, request)

    assert ranked["eligible"].tolist() == [True, False]
    assert ranked.iloc[0]["sharpe"] == 1.0
