"""Grid-search backtest optimization with persisted experiment results."""

from __future__ import annotations

import itertools
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from quant_platform.application.backtest_service import BacktestRequest, BacktestService

OBJECTIVES = {
    "sharpe": "夏普比率",
    "annual_return": "年化收益",
    "calmar": "卡玛比率",
    "max_drawdown": "最大回撤最小",
}


@dataclass(frozen=True)
class OptimizationRequest:
    """Inputs for a bounded, reproducible grid search."""

    base_request: BacktestRequest
    parameter_grid: dict[str, tuple[Any, ...]]
    objective: str = "sharpe"
    max_drawdown_limit: float | None = None
    max_combinations: int = 100


@dataclass(frozen=True)
class OptimizationResult:
    """Ranked experiments and their persisted directory."""

    optimization_id: str
    experiments: pd.DataFrame
    output_dir: Path


class OptimizationService:
    """Run strategy parameter combinations through the normal backtest service."""

    def __init__(self, backtests: BacktestService) -> None:
        self.backtests = backtests

    @property
    def root(self) -> Path:
        return self.backtests.runs_root.parent / "optimizations"

    def combination_count(self, request: OptimizationRequest) -> int:
        """Return the cartesian-product size without executing it."""

        count = 1
        for values in request.parameter_grid.values():
            count *= len(values)
        return count

    def run(self, request: OptimizationRequest) -> OptimizationResult:
        """Execute, rank, and persist a complete grid search."""

        if request.objective not in OBJECTIVES:
            raise ValueError(f"Unsupported optimization objective: {request.objective}")
        if not request.parameter_grid:
            raise ValueError("parameter_grid must not be empty")
        if any(not values for values in request.parameter_grid.values()):
            raise ValueError("every optimized parameter needs at least one value")
        count = self.combination_count(request)
        if count > request.max_combinations:
            raise ValueError(
                f"Parameter grid has {count} combinations; maximum is {request.max_combinations}"
            )
        if request.max_drawdown_limit is not None and not (
            0.0 <= request.max_drawdown_limit <= 1.0
        ):
            raise ValueError("max_drawdown_limit must be between 0 and 1")

        names = list(request.parameter_grid)
        rows: list[dict[str, Any]] = []
        for index, values in enumerate(
            itertools.product(*(request.parameter_grid[name] for name in names)),
            start=1,
        ):
            parameters = dict(request.base_request.strategy_parameters)
            parameters.update(dict(zip(names, values, strict=True)))
            effective = replace(
                request.base_request,
                strategy_id=f"{request.base_request.strategy_id}_opt_{index:03d}",
                strategy_parameters=parameters,
            )
            row: dict[str, Any] = {
                **{f"param_{name}": value for name, value in parameters.items()},
                "status": "SUCCESS",
                "run_id": None,
                "error": None,
            }
            try:
                completed = self.backtests.run(effective)
                row["run_id"] = completed.result.run_id
                row.update(completed.result.summary)
            except Exception as exc:
                row["status"] = "FAILED"
                row["error"] = f"{type(exc).__name__}: {exc}"[:2000]
            rows.append(row)

        experiments = self._rank(pd.DataFrame(rows), request)
        optimization_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        output = self.root / optimization_id
        output.mkdir(parents=True, exist_ok=False)
        experiments.to_csv(output / "results.csv", index=False, encoding="utf-8-sig")
        (output / "request.json").write_text(
            json.dumps(
                {
                    "optimization_id": optimization_id,
                    "objective": request.objective,
                    "max_drawdown_limit": request.max_drawdown_limit,
                    "parameter_grid": request.parameter_grid,
                    "combination_count": count,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        return OptimizationResult(optimization_id, experiments, output)

    @staticmethod
    def _rank(experiments: pd.DataFrame, request: OptimizationRequest) -> pd.DataFrame:
        frame = experiments.copy()
        objective = pd.to_numeric(
            frame.get(request.objective, pd.Series(index=frame.index, dtype=float)),
            errors="coerce",
        )
        eligible = frame["status"].eq("SUCCESS") & objective.notna()
        if request.max_drawdown_limit is not None:
            drawdown_source = (
                frame["max_drawdown"]
                if "max_drawdown" in frame
                else pd.Series(index=frame.index, dtype=float)
            )
            drawdown = pd.to_numeric(drawdown_source, errors="coerce")
            eligible &= drawdown.ge(-request.max_drawdown_limit)
        frame["eligible"] = eligible
        frame["objective_value"] = objective
        frame = frame.sort_values(
            ["eligible", "objective_value"], ascending=[False, False], na_position="last"
        ).reset_index(drop=True)
        frame["rank"] = pd.Series(
            range(1, int(frame["eligible"].sum()) + 1),
            index=frame.index[frame["eligible"]],
            dtype="Int64",
        )
        return frame
