from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import cast

from quant_platform.application.backtest_service import BacktestRequest, BacktestService
from quant_platform.application.walk_forward_service import (
    WalkForwardRequest,
    WalkForwardService,
)


class _FakeBacktests:
    def __init__(self, root: Path) -> None:
        self.runs_root = root / "runs"
        self.calls: list[BacktestRequest] = []

    def run(self, request: BacktestRequest) -> SimpleNamespace:
        self.calls.append(request)
        short_window = int(request.strategy_parameters["short_window"])
        if request.evaluation_mode == "training":
            summary = {
                "sharpe": short_window / 10.0,
                "annual_return": short_window / 100.0,
                "max_drawdown": -0.10,
                "calmar": 1.0,
            }
        else:
            summary = {
                "cumulative_return": 0.10,
                "annual_return": 0.10,
                "max_drawdown": -0.05,
                "sharpe": 1.0,
                "metrics_reliable": True,
            }
        result = SimpleNamespace(run_id=f"run-{len(self.calls)}", summary=summary)
        return SimpleNamespace(result=result)


def test_walk_forward_selects_on_training_and_tests_unseen_windows(tmp_path: Path) -> None:
    fake = _FakeBacktests(tmp_path)
    service = WalkForwardService(cast(BacktestService, fake))
    base = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="walk",
        strategy_parameters={"short_window": 10},
        start_date=date(2022, 1, 1),
        end_date=date(2022, 12, 31),
        initial_cash=1_000_000,
        top_n=2,
        rebalance="weekly",
    )
    request = WalkForwardRequest(
        base_request=base,
        parameter_grid={"short_window": (10, 20)},
        training_months=6,
        test_months=3,
        step_months=3,
        max_windows=2,
    )

    result = service.run(request)

    tests = [call for call in fake.calls if call.evaluation_mode == "out_of_sample"]
    assert len(tests) == 2
    assert all(call.strategy_parameters["short_window"] == 20 for call in tests)
    assert result.summary["successful_windows"] == 2
    assert abs(result.summary["out_of_sample_cumulative_return"] - 0.21) < 1e-9
    assert (result.output_dir / "results.csv").exists()
