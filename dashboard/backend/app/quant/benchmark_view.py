"""Benchmark comparison for one persisted backtest, read from its run directory.

The engine already writes the benchmark's equity next to the strategy's (``nav.parquet``)
and the relative statistics (``summary.json``); this module only turns them into what the
result page shows. Reading at request time means runs made before the page existed get it too.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.application.benchmarks import BENCHMARK_NAMES


def _number(value: Any, scale: float = 1.0, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number * scale, digits) if math.isfinite(number) else None


def benchmark_comparison(directory: Path | None) -> dict[str, Any] | None:
    """Return curves and relative metrics, or ``None`` when the run recorded no benchmark.

    Percent fields are already multiplied by 100. When the benchmark's bars start after the
    backtest does, the two returns cover different periods, so nothing is compared: the result
    carries ``comparable: False`` and the date the benchmark starts instead of the numbers.
    """

    if directory is None:
        return None
    try:
        nav = pd.read_parquet(directory / "nav.parquet")
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(summary, dict) or not {"trade_date", "equity", "benchmark_equity"} <= set(nav.columns):
        return None
    nav = nav.sort_values("trade_date")
    benchmark = pd.to_numeric(nav["benchmark_equity"], errors="coerce")
    equity = pd.to_numeric(nav["equity"], errors="coerce")
    if benchmark.notna().sum() < 2:
        return None
    symbol = str(summary.get("benchmark_symbol") or "")
    result: dict[str, Any] = {"symbol": symbol, "name": BENCHMARK_NAMES.get(symbol, symbol or "基准"), "comparable": False}
    if pd.isna(benchmark.iloc[0]) or equity.isna().any():
        covered = nav.loc[benchmark.notna(), "trade_date"].iloc[0]
        result["benchmark_start"] = pd.Timestamp(covered).date().isoformat()
        return result
    # 引擎把基准的第一天换算成初始资金，所以两条曲线从同一个起点出发。
    initial = float(benchmark.iloc[0])
    if initial <= 0:
        return None
    benchmark = benchmark.ffill()
    drawdown = 1.0 - benchmark / benchmark.cummax()
    result.update({
        "comparable": True,
        "strategy_curve": [round(float(value), 2) for value in (equity / initial - 1.0) * 100],
        "benchmark_curve": [round(float(value), 2) for value in (benchmark / initial - 1.0) * 100],
        "benchmark_return": _number(summary.get("benchmark_return"), 100),
        "excess_return": _number(summary.get("excess_return"), 100),
        "benchmark_max_drawdown": _number(drawdown.max(), 100),
        "beta": _number(summary.get("beta")),
        "alpha": _number(summary.get("regression_alpha"), 100),
        "information_ratio": _number(summary.get("information_ratio")),
        "tracking_error": _number(summary.get("tracking_error"), 100),
    })
    return result
