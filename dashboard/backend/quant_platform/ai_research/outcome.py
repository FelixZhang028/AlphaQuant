"""What happened after an analysis: the stock's move from the analysis day to its newest local bar, next to 沪深300.

This is how a user can judge the readings over time. It is computed when a list is shown, from
the local data as it is then, so it grows as new bars are downloaded. Stock moves use adjusted
closes (a dividend is not a fall); the index uses its closes on the same two days.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

BENCHMARK = "000300.SH"
BENCHMARK_NAME = "沪深300"


def _close_on_or_before(series: pd.Series, day: pd.Timestamp) -> float | None:
    earlier = series[series.index <= day]
    return float(earlier.iloc[-1]) if not earlier.empty else None


def later_moves(repository: Any, analyses: list[tuple[str, date]]) -> dict[tuple[str, date], dict[str, Any] | None]:
    """For each (symbol, analysis day): ``{end_date, days, change, benchmark_change}``; None while there is no later bar."""

    if not analyses:
        return {}
    symbols = sorted({symbol for symbol, _ in analyses})
    start = min(day for _, day in analyses)
    bars = repository.get_daily_bars(symbols, start_date=start)
    closes = {symbol: frame.set_index("trade_date")["adjusted_close"].dropna().sort_index()
              for symbol, frame in bars.groupby("symbol")} if not bars.empty else {}
    index = repository.read_table("benchmark_bars")
    if not index.empty:
        index = index[index["symbol"] == BENCHMARK]
        index = pd.Series(index["raw_close"].to_numpy(dtype=float), index=pd.to_datetime(index["trade_date"]).dt.normalize()).sort_index()
    else:
        index = pd.Series(dtype=float, index=pd.DatetimeIndex([]))

    result: dict[tuple[str, date], dict[str, Any] | None] = {}
    for symbol, day in analyses:
        series = closes.get(symbol)
        begin = pd.Timestamp(day)
        if series is None or series.empty or series.index.max() <= begin:
            result[(symbol, day)] = None
            continue
        first, end = series.get(begin), series.index.max()
        if first is None or pd.isna(first):
            result[(symbol, day)] = None
            continue
        move: dict[str, Any] = {
            "end_date": end.date().isoformat(),
            "days": int(((series.index > begin) & (series.index <= end)).sum()),
            "change": float(series.iloc[-1]) / float(first) - 1,
            "benchmark": BENCHMARK_NAME,
            "benchmark_change": None,
        }
        base, last = _close_on_or_before(index, begin), _close_on_or_before(index, end)
        if base and last and not index.empty and index.index.max() >= end:
            move["benchmark_change"] = last / base - 1
        result[(symbol, day)] = move
    return result
