"""Real parameter search and rolling out-of-sample validation built on one saved backtest."""
from __future__ import annotations

import json
import math
import re
from copy import deepcopy
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.application.backtest_service import BacktestRequest, BacktestService
from quant_platform.application.optimization_service import (
    OBJECTIVES,
    OptimizationRequest,
    OptimizationService,
)
from quant_platform.application.walk_forward_service import WalkForwardRequest, WalkForwardService
from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.spec import ParameterKind, StrategyMetadata, StrategyParameter

# Requests run synchronously, so both limits bound how long one click can take.
MAX_COMBINATIONS = 24
MAX_BACKTESTS = 100
_PERCENT_OBJECTIVES = {"annual_return", "max_drawdown"}


class ResearchInputError(ValueError):
    """A request the user can fix; the message is shown as-is."""


def _tunable(parameter: StrategyParameter) -> bool:
    # Free text (for example a rule definition) has no meaningful candidate grid.
    return parameter.kind != ParameterKind.STRING or bool(parameter.choices)


REBALANCE_LABELS = {"daily": "每日", "weekly": "每周", "monthly": "每月"}


def research_parameters(metadata: StrategyMetadata) -> tuple[StrategyParameter, ...]:
    """The strategy's own tunable parameters, then the two settings every strategy shares."""
    own = tuple(p for p in metadata.parameters if _tunable(p))
    shared = (
        StrategyParameter("top_n", "持股数量", ParameterKind.INTEGER, 10, "每次调仓后持有的股票数量", minimum=1,
                          maximum=50 if metadata.plugin_name == "rule_builder" else 500),
        StrategyParameter("rebalance", "调仓频率", ParameterKind.STRING, "weekly",
                          "，".join(f"{value} 表示{label}" for value, label in REBALANCE_LABELS.items()),
                          choices=tuple(REBALANCE_LABELS)),
    )
    names = {p.name for p in own}
    return (*own, *(p for p in shared if p.name not in names))


def tunable_parameters(metadata: StrategyMetadata, current: dict[str, Any], *, top_n: Any = None,
                       rebalance: Any = None) -> list[dict[str, Any]]:
    """Parameters offered for search with their value in the baseline run."""
    baseline = {"top_n": top_n, "rebalance": rebalance, **current}
    return [{"name": p.name, "label": p.label, "kind": p.kind.value, "description": p.description,
             "current": p.default if baseline.get(p.name) is None else baseline[p.name],
             "minimum": p.minimum, "maximum": p.maximum, "choices": list(p.choices),
             "choice_labels": REBALANCE_LABELS if p.name == "rebalance" and p.choices == tuple(REBALANCE_LABELS) else {}}
            for p in research_parameters(metadata)]


def baseline_request(service: BacktestService, run_id: str) -> tuple[BacktestRequest, StrategyMetadata]:
    """Rebuild the saved run's request; every trial then differs from it only in the searched parameters."""
    try:
        snapshot = service.run_store.load_config(run_id)
        request = service.request_from_run(run_id)
        metadata = service.catalog.get_metadata(request.strategy_plugin)
    except (OSError, KeyError, TypeError, ValueError, ConfigurationError) as exc:
        raise ResearchInputError("这条回测记录的配置无法读取，或它的策略已不存在，不能作为基准。") from exc
    # The baseline's own stock pool, not whatever the pool has since become.
    service.configs["universe"] = deepcopy(snapshot["universe"])
    return request, metadata


def parameter_grid(metadata: StrategyMetadata, raw: dict[str, list[Any]]) -> dict[str, tuple[Any, ...]]:
    definitions = {p.name: p for p in research_parameters(metadata)}
    grid: dict[str, tuple[Any, ...]] = {}
    for name, values in raw.items():
        definition = definitions.get(name)
        if definition is None:
            raise ResearchInputError(f"策略没有名为 {name} 的可调参数，可选：{'、'.join(definitions)}。")
        parsed: list[Any] = []
        for value in values:
            try:
                candidate = definition.parse(value)
            except ConfigurationError as exc:
                limits = "" if definition.minimum is None and definition.maximum is None else (
                    f"（允许范围 {definition.minimum if definition.minimum is not None else '不限'} ~ "
                    f"{definition.maximum if definition.maximum is not None else '不限'}）")
                if definition.choices:
                    limits = f"（可选 {' / '.join(definition.choices)}）"
                raise ResearchInputError(f"参数「{definition.label}」的候选值 {value} 无效{limits}。") from exc
            if candidate not in parsed:
                parsed.append(candidate)
        if parsed:
            grid[name] = tuple(parsed)
    if not grid:
        raise ResearchInputError("请至少为一个参数填写候选值。")
    count = math.prod(len(values) for values in grid.values())
    if count > MAX_COMBINATIONS:
        raise ResearchInputError(f"候选值共有 {count} 种组合，超过上限 {MAX_COMBINATIONS} 种，请减少候选值。")
    return grid


def _finite(value: Any) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if math.isfinite(number) else None


def _percent(value: Any, absolute: bool = False) -> float | None:
    number = _finite(value)
    return None if number is None else round((abs(number) if absolute else number) * 100, 2)


def _rounded(value: Any, digits: int = 4) -> float | None:
    number = _finite(value)
    return None if number is None else round(number, digits)


def _native(value: Any) -> Any:
    value = value.item() if hasattr(value, "item") else value
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _text(value: Any) -> str | None:
    return None if value is None or (isinstance(value, float) and math.isnan(value)) else str(value)


def _reason(value: Any) -> str | None:
    """A failed trial's reason without the exception class and engine code in front of it."""
    text = _text(value)
    return None if text is None else re.sub(r"^(?:\w+(?:Error|Exception):\s*)?(?:[A-Z][A-Z_]{2,}:\s*)?", "", text)


def _objective(value: Any, objective: str) -> float | None:
    return _percent(value, objective == "max_drawdown") if objective in _PERCENT_OBJECTIVES else _rounded(value)


def _drawdown_limit(value: float | None) -> float | None:
    return value if value and value > 0 else None


def run_optimization(service: BacktestService, base: BacktestRequest, grid: dict[str, tuple[Any, ...]], *,
                     objective: str, max_drawdown_limit: float | None, baseline_run_id: str) -> dict[str, Any]:
    if objective not in OBJECTIVES:
        raise ResearchInputError("不支持的排序指标。")
    result = OptimizationService(service).run(OptimizationRequest(
        base_request=base, parameter_grid=grid, objective=objective,
        max_drawdown_limit=_drawdown_limit(max_drawdown_limit), max_combinations=MAX_COMBINATIONS,
        baseline_run_id=baseline_run_id))
    rows = []
    for row in result.experiments.to_dict("records"):
        rows.append({
            "rank": None if pd.isna(row.get("rank")) else int(row["rank"]),
            "eligible": bool(row.get("eligible")), "status": str(row.get("status")),
            "error": _reason(row.get("error")), "run_id": _text(row.get("run_id")),
            "parameters": {name: _native(row.get(f"param_{name}")) for name in grid},
            "objective_value": _objective(row.get("objective_value"), objective),
            "cumulative_return": _percent(row.get("cumulative_return")),
            "annual_return": _percent(row.get("annual_return")),
            "max_drawdown": _percent(row.get("max_drawdown"), True), "sharpe": _rounded(row.get("sharpe"), 2),
            "dsr": _rounded(row.get("dsr")), "selection_bias_status": _text(row.get("selection_bias_status")),
            "selection_bias_reason": _text(row.get("selection_bias_reason")),
        })
    best = next((row for row in rows if row["rank"] == 1), None)
    return {"optimization_id": result.optimization_id, "objective": objective, "combination_count": len(rows),
            "start_date": base.start_date.isoformat(), "end_date": base.end_date.isoformat(),
            "results": rows,
            # How much of the winner's edge may come from having tried several combinations.
            "selection_bias": None if best is None else {
                "status": best["selection_bias_status"], "message": best["selection_bias_reason"], "dsr": best["dsr"]}}


def walk_forward_range(bounds: tuple[date, date], *, training_months: int, test_months: int,
                       step_months: int, max_windows: int) -> tuple[date, date]:
    """The most recent stretch of local data that fits the requested windows, ending on the last bar."""
    local_start, local_end = bounds
    months = training_months + test_months + step_months * (max_windows - 1)
    start = (pd.Timestamp(local_end) + pd.Timedelta(days=1) - pd.DateOffset(months=months)).date()
    return max(start, local_start), local_end


def run_walk_forward(service: BacktestService, base: BacktestRequest, grid: dict[str, tuple[Any, ...]], *,
                     objective: str, training_months: int, test_months: int, step_months: int,
                     max_windows: int, baseline_run_id: str) -> dict[str, Any]:
    if objective not in OBJECTIVES:
        raise ResearchInputError("不支持的排序指标。")
    request = WalkForwardRequest(
        base_request=base, parameter_grid=grid, objective=objective, training_months=training_months,
        test_months=test_months, step_months=step_months, max_windows=max_windows,
        max_combinations=MAX_COMBINATIONS, baseline_run_id=baseline_run_id)
    walker = WalkForwardService(service)
    try:
        windows = walker.build_windows(request)
    except ValueError as exc:
        raise ResearchInputError(str(exc)) from exc
    backtests = len(windows) * (math.prod(len(values) for values in grid.values()) + 1)
    if backtests > MAX_BACKTESTS:
        raise ResearchInputError(
            f"这次验证需要运行 {backtests} 次回测，超过上限 {MAX_BACKTESTS} 次，请减少候选值或窗口数。")
    result = walker.run(request)
    rows = []
    for row in result.windows.to_dict("records"):
        try:
            selected = json.loads(row.get("selected_parameters") or "{}")
        except (TypeError, ValueError):
            selected = {}
        rows.append({
            "window": int(row["window"]), "status": str(row.get("status")), "error": _reason(row.get("error")),
            **{key: pd.Timestamp(row[key]).date().isoformat() for key in ("train_start", "train_end", "test_start", "test_end")},
            "train_run_id": _text(row.get("train_run_id")), "test_run_id": _text(row.get("test_run_id")),
            "selected_parameters": {name: selected.get(name) for name in grid if name in selected},
            "train_objective_value": _objective(row.get("train_objective_value"), objective),
            "test_cumulative_return": _percent(row.get("test_cumulative_return")),
            "test_max_drawdown": _percent(row.get("test_max_drawdown"), True),
            "test_sharpe": _rounded(row.get("test_sharpe"), 2),
        })
    summary = result.summary
    return {"validation_id": result.validation_id, "objective": objective, "window_count": len(rows),
            "backtest_count": backtests, "start_date": base.start_date.isoformat(), "end_date": base.end_date.isoformat(),
            "summary": {
                "successful_windows": int(summary.get("successful_windows") or 0),
                "failed_windows": int(summary.get("failed_windows") or 0),
                "out_of_sample_cumulative_return": _percent(summary.get("out_of_sample_cumulative_return")),
                "average_window_return": _percent(summary.get("average_window_return")),
                "positive_window_ratio": _percent(summary.get("positive_window_ratio")),
                "worst_window_drawdown": _percent(summary.get("worst_window_drawdown"), True),
                "average_window_sharpe": _rounded(summary.get("average_window_sharpe"), 2),
                "trust_warning": summary.get("trust_warning"),
            },
            "windows": rows}
