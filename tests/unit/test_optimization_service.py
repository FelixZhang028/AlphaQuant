from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.optimization_service import (
    OptimizationRequest,
    OptimizationService,
)


class _FakeBacktests:
    def __init__(self, root: Path, request: BacktestRequest) -> None:
        self.runs_root = root / "runs"
        self.request = request

    def run(self, request: BacktestRequest) -> SimpleNamespace:
        value = int(request.strategy_parameters["lookback"])
        summary = {
            "sharpe": value / 10.0,
            "annual_return": value / 100.0,
            "max_drawdown": -value / 100.0,
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
    )

    result = service.run(request)

    assert result.experiments.iloc[0]["param_lookback"] == 20
    assert result.experiments.iloc[0]["rank"] == 1
    assert result.experiments["eligible"].tolist() == [True, True, False]
    assert (result.output_dir / "results.csv").exists()
