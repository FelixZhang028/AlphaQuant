"""Rolling out-of-sample validation for strategy parameter research."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pandas as pd

from quant_platform.application.backtest_service import BacktestRequest, BacktestService
from quant_platform.application.optimization_service import (
    OBJECTIVES,
    OptimizationRequest,
    OptimizationService,
)


@dataclass(frozen=True)
class WalkForwardWindow:
    """One non-overlapping training and out-of-sample test window."""

    train_start: date
    train_end: date
    test_start: date
    test_end: date


@dataclass(frozen=True)
class WalkForwardRequest:
    """Configuration for rolling parameter selection and unseen-period testing."""

    base_request: BacktestRequest
    parameter_grid: dict[str, tuple[Any, ...]]
    objective: str = "sharpe"
    training_months: int = 12
    test_months: int = 3
    step_months: int = 3
    max_windows: int = 12
    max_drawdown_limit: float | None = None
    max_combinations: int = 100
    baseline_run_id: str | None = None


@dataclass(frozen=True)
class WalkForwardResult:
    """Persisted rolling out-of-sample experiments and aggregate statistics."""

    validation_id: str
    windows: pd.DataFrame
    summary: dict[str, Any]
    output_dir: Path


class WalkForwardService:
    """Select parameters on past data and evaluate them only on later unseen data."""

    def __init__(self, backtests: BacktestService) -> None:
        self.backtests = backtests

    @property
    def root(self) -> Path:
        return self.backtests.runs_root.parent / "walk_forward"

    def build_windows(self, request: WalkForwardRequest) -> tuple[WalkForwardWindow, ...]:
        """Build fixed-length rolling windows without overlapping test periods."""

        self._validate(request)
        windows: list[WalkForwardWindow] = []
        train_start = request.base_request.start_date
        overall_end = request.base_request.end_date
        while len(windows) < request.max_windows:
            train_end = _add_months(train_start, request.training_months) - timedelta(days=1)
            test_start = train_end + timedelta(days=1)
            test_end = _add_months(test_start, request.test_months) - timedelta(days=1)
            if test_end > overall_end:
                break
            windows.append(WalkForwardWindow(train_start, train_end, test_start, test_end))
            train_start = _add_months(train_start, request.step_months)
        if not windows:
            raise ValueError("所选日期不足以形成一个完整的训练期和样本外测试期")
        return tuple(windows)

    def run(self, request: WalkForwardRequest) -> WalkForwardResult:
        """Optimize each training window and run the winner on its unseen test window."""

        windows = self.build_windows(request)
        validation_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        optimizer = OptimizationService(self.backtests)
        rows: list[dict[str, Any]] = []
        for index, window in enumerate(windows, start=1):
            row: dict[str, Any] = {
                "window": index,
                "train_start": window.train_start,
                "train_end": window.train_end,
                "test_start": window.test_start,
                "test_end": window.test_end,
                "status": "SUCCESS",
                "error": None,
            }
            try:
                training_base = replace(
                    request.base_request,
                    strategy_id=f"{request.base_request.strategy_id}_wf{index:02d}_train",
                    start_date=window.train_start,
                    end_date=window.train_end,
                    evaluation_mode="training",
                )
                optimized = optimizer.run(
                    OptimizationRequest(
                        base_request=training_base,
                        parameter_grid=request.parameter_grid,
                        objective=request.objective,
                        max_drawdown_limit=request.max_drawdown_limit,
                        max_combinations=request.max_combinations,
                        baseline_run_id=request.baseline_run_id,
                    )
                )
                eligible = optimized.experiments[optimized.experiments["eligible"].eq(True)]
                if eligible.empty:
                    raise ValueError("训练期没有找到满足约束的参数")
                best = eligible.iloc[0]
                parameters = dict(request.base_request.strategy_parameters)
                for name in request.parameter_grid:
                    parameters[name] = _native(best[f"param_{name}"])
                test_request = replace(
                    request.base_request,
                    strategy_id=f"{request.base_request.strategy_id}_wf{index:02d}_test",
                    strategy_parameters=parameters,
                    start_date=window.test_start,
                    end_date=window.test_end,
                    evaluation_mode="out_of_sample",
                    run_kind="walk_forward_oos",
                    parent_experiment_id=validation_id,
                    baseline_run_id=request.baseline_run_id,
                )
                tested = self.backtests.run(test_request)
                row.update(
                    {
                        "optimization_id": optimized.optimization_id,
                        "train_run_id": best.get("run_id"),
                        "test_run_id": tested.result.run_id,
                        "selected_parameters": json.dumps(
                            parameters, ensure_ascii=False, sort_keys=True, default=str
                        ),
                        "train_objective_value": _native(best.get("objective_value")),
                        **{
                            f"test_{key}": value
                            for key, value in tested.result.summary.items()
                            if isinstance(value, (int, float, str, bool)) or value is None
                        },
                    }
                )
            except Exception as exc:
                row["status"] = "FAILED"
                row["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            rows.append(row)

        frame = pd.DataFrame(rows)
        summary = _aggregate(frame)
        output = self.root / validation_id
        output.mkdir(parents=True, exist_ok=False)
        frame.to_csv(output / "results.csv", index=False, encoding="utf-8-sig")
        (output / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        (output / "request.json").write_text(
            json.dumps(
                {
                    "validation_id": validation_id,
                    "objective": request.objective,
                    "parameter_grid": request.parameter_grid,
                    "training_months": request.training_months,
                    "test_months": request.test_months,
                    "step_months": request.step_months,
                    "max_windows": request.max_windows,
                    "max_drawdown_limit": request.max_drawdown_limit,
                    "window_count": len(windows),
                    "baseline_run_id": request.baseline_run_id,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return WalkForwardResult(validation_id, frame, summary, output)

    @staticmethod
    def _validate(request: WalkForwardRequest) -> None:
        if request.objective not in OBJECTIVES:
            raise ValueError(f"Unsupported optimization objective: {request.objective}")
        if request.training_months <= 0 or request.test_months <= 0 or request.step_months <= 0:
            raise ValueError("训练、测试和滚动月数必须为正数")
        if request.step_months < request.test_months:
            raise ValueError("滚动步长不能小于测试月数，否则样本外区间会重叠")
        if request.max_windows <= 0:
            raise ValueError("最大窗口数必须为正数")
        if not request.parameter_grid or any(
            not values for values in request.parameter_grid.values()
        ):
            raise ValueError("至少需要一个包含候选值的策略参数")


def _add_months(value: date, months: int) -> date:
    return (pd.Timestamp(value) + pd.DateOffset(months=months)).date()


def _native(value: Any) -> Any:
    return value.item() if hasattr(value, "item") else value


def _numeric_column(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").dropna()


def _aggregate(frame: pd.DataFrame) -> dict[str, Any]:
    successful = frame[frame["status"].eq("SUCCESS")]
    returns = _numeric_column(successful, "test_cumulative_return")
    drawdowns = _numeric_column(successful, "test_max_drawdown")
    sharpes = _numeric_column(successful, "test_sharpe")
    compounded = (
        float(cast(Any, returns.add(1.0).prod())) - 1.0 if not returns.empty else None
    )
    average_sharpe = float(sharpes.mean()) if not sharpes.empty else None
    if average_sharpe is not None and not math.isfinite(average_sharpe):
        average_sharpe = None
    return {
        "validation_mode": "ROLLING_OUT_OF_SAMPLE",
        "window_count": len(frame),
        "successful_windows": len(successful),
        "failed_windows": len(frame) - len(successful),
        "out_of_sample_cumulative_return": compounded,
        "average_window_return": float(returns.mean()) if not returns.empty else None,
        "positive_window_ratio": float((returns > 0).mean()) if not returns.empty else None,
        "worst_window_drawdown": float(drawdowns.min()) if not drawdowns.empty else None,
        "average_window_sharpe": average_sharpe,
        "trust_warning": "固定股票池仍可能存在事后选股偏差。",
    }
