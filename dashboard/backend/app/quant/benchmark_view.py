"""Benchmark comparison for one persisted backtest, read from its run directory.

The engine already writes the benchmark's equity next to the strategy's (``nav.parquet``)
and the relative statistics (``summary.json``); this module turns them into what the result
page shows. Reading at request time means runs made before the page existed get it too.

A run records one benchmark. Comparing with another index recomputes the same statistics
from the locally stored index bars, anchored the way the engine anchors its own.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.application.benchmarks import BENCHMARK_NAMES
from quant_platform.backtest.relative_metrics import relative_metrics

# 回测结束前，基准最多可以缺这么多个交易日的行情（指数行情常常比个股晚一两天更新）。
MAX_TRAILING_DAYS_WITHOUT_BENCHMARK = 5


def _number(value: Any, scale: float = 1.0, digits: int = 2) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number * scale, digits) if math.isfinite(number) else None


def _day(value: Any) -> str:
    return pd.Timestamp(value).date().isoformat()


def benchmark_options(bars: pd.DataFrame) -> list[dict[str, str]]:
    """Indices with local bars, in the usual display order, with the dates they cover."""

    if bars.empty or not {"symbol", "trade_date", "raw_close"} <= set(bars.columns):
        return []
    valid = bars[pd.to_numeric(bars["raw_close"], errors="coerce") > 0]
    spans = valid.groupby(valid["symbol"].astype(str))["trade_date"].agg(["min", "max"])
    return [{"symbol": symbol, "name": name, "start_date": _day(spans.loc[symbol, "min"]), "end_date": _day(spans.loc[symbol, "max"])}
            for symbol, name in BENCHMARK_NAMES.items() if symbol in spans.index]


def _equity_from_bars(nav: pd.DataFrame, bars: pd.DataFrame, symbol: str, initial: float) -> pd.Series | dict[str, str] | None:
    """The index as equity on the run's own trading days, anchored like the engine's benchmark:
    the first close inside the run equals the initial cash; days before it stay missing.

    ``None`` when the index has no local bars at all; when it has bars but (almost) none on the
    run's days, the date its bars start or stop, so the page can say why nothing is compared.
    """

    selected = bars[bars["symbol"].astype(str).eq(symbol)]
    closes = pd.to_numeric(selected["raw_close"], errors="coerce")
    closes.index = pd.to_datetime(selected["trade_date"]).dt.normalize()
    closes = closes[closes > 0]
    closes = closes[~closes.index.duplicated(keep="last")].sort_index()
    if closes.empty:
        return None
    days = pd.to_datetime(nav["trade_date"]).dt.normalize()
    on_run_days = closes.reindex(days)
    if on_run_days.notna().sum() < 2:
        if closes.index[0] > days.iloc[0]:
            return {"benchmark_start": _day(closes.index[0])}
        return {"benchmark_end": _day(closes.index[-1])}
    anchored = on_run_days / on_run_days.dropna().iloc[0] * initial
    anchored.index = nav.index
    return anchored


def benchmark_comparison(directory: Path | None, symbol: str | None = None,
                         bars: pd.DataFrame | None = None) -> dict[str, Any] | None:
    """Return curves and relative metrics, or ``None`` when there is nothing to compare with.

    Without ``symbol`` the run's recorded benchmark is used as the engine saved it. With another
    ``symbol`` the comparison is recomputed from ``bars`` (the local ``benchmark_bars`` table).

    Percent fields are already multiplied by 100. When the index's bars do not span the run,
    the two returns would cover different periods, so nothing is compared: the result carries
    ``comparable: False`` with ``benchmark_start`` or ``benchmark_end`` instead of the numbers.
    """

    if directory is None:
        return None
    try:
        nav = pd.read_parquet(directory / "nav.parquet")
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(summary, dict) or not {"trade_date", "equity"} <= set(nav.columns):
        return None
    nav = nav.sort_values("trade_date").reset_index(drop=True)
    equity = pd.to_numeric(nav["equity"], errors="coerce")
    recorded = str(summary.get("benchmark_symbol") or "")
    chosen = symbol or recorded
    stale_days = 0
    if chosen == recorded and "benchmark_equity" in nav.columns:
        benchmark = pd.to_numeric(nav["benchmark_equity"], errors="coerce")
        metrics = summary
    else:
        initial_cash = _number(summary.get("initial_cash"), digits=6)
        if bars is None or not chosen or not initial_cash or initial_cash <= 0:
            return None
        benchmark = _equity_from_bars(nav, bars, chosen, initial_cash)
        if benchmark is None:
            return None
        if isinstance(benchmark, dict):
            return {"symbol": chosen, "name": BENCHMARK_NAMES.get(chosen, chosen), "comparable": False, **benchmark}
        stale_days = int(benchmark.isna().iloc[::-1].cumprod().sum())
        metrics = relative_metrics(
            nav.assign(benchmark_equity=benchmark.ffill()),
            int(summary.get("annualization") or 252), float(summary.get("risk_free_rate") or 0.0))
        present = benchmark.dropna()
        metrics["benchmark_return"] = float(present.iloc[-1]) / float(present.iloc[0]) - 1.0
        cumulative = _number(summary.get("cumulative_return"), digits=10)
        metrics["excess_return"] = None if cumulative is None else cumulative - metrics["benchmark_return"]
    if benchmark.notna().sum() < 2:
        return None
    result: dict[str, Any] = {"symbol": chosen, "name": BENCHMARK_NAMES.get(chosen, chosen or "基准"), "comparable": False}
    if pd.isna(benchmark.iloc[0]) or equity.isna().any():
        result["benchmark_start"] = _day(nav.loc[benchmark.notna(), "trade_date"].iloc[0])
        return result
    if stale_days > MAX_TRAILING_DAYS_WITHOUT_BENCHMARK:
        result["benchmark_end"] = _day(nav.loc[benchmark.notna(), "trade_date"].iloc[-1])
        return result
    # 基准的第一天等于初始资金，所以两条曲线从同一个起点出发。
    initial = float(benchmark.iloc[0])
    if initial <= 0:
        return None
    benchmark = benchmark.ffill()
    drawdown = 1.0 - benchmark / benchmark.cummax()
    result.update({
        "comparable": True,
        "strategy_curve": [round(float(value), 2) for value in (equity / initial - 1.0) * 100],
        "benchmark_curve": [round(float(value), 2) for value in (benchmark / initial - 1.0) * 100],
        "benchmark_return": _number(metrics.get("benchmark_return"), 100),
        "excess_return": _number(metrics.get("excess_return"), 100),
        "benchmark_max_drawdown": _number(drawdown.max(), 100),
        "beta": _number(metrics.get("beta")),
        "alpha": _number(metrics.get("regression_alpha"), 100),
        "information_ratio": _number(metrics.get("information_ratio")),
        "tracking_error": _number(metrics.get("tracking_error"), 100),
    })
    return result
