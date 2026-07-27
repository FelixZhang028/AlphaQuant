"""Coverage and quality summaries for local daily market data."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class DatasetCoverage:
    """Compact dataset-level coverage information for CLI and web."""

    rows: int
    symbol_count: int
    start_date: date | None
    end_date: date | None
    expected_rows: int
    missing_rows: int
    coverage_ratio: float
    duplicate_rows: int
    unknown_status_rows: int
    missing_price_rows: int

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-friendly values."""

        return asdict(self)


def calculate_daily_coverage(
    bars: pd.DataFrame,
    calendar: pd.DataFrame,
    symbols: list[str] | None = None,
) -> tuple[DatasetCoverage, pd.DataFrame]:
    """Calculate overall and per-symbol completeness inside stored date bounds."""

    if bars.empty:
        empty = DatasetCoverage(0, 0, None, None, 0, 0, 0.0, 0, 0, 0)
        return empty, pd.DataFrame(
            columns=[
                "symbol",
                "rows",
                "start_date",
                "end_date",
                "expected_rows",
                "missing_rows",
                "coverage_ratio",
                "unknown_status_rows",
            ]
        )

    frame = bars.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
    selected_symbols = sorted(
        set(symbols) if symbols else set(frame["symbol"].astype(str))
    )
    frame = frame[frame["symbol"].isin(selected_symbols)]
    if frame.empty:
        empty = DatasetCoverage(0, len(selected_symbols), None, None, 0, 0, 0.0, 0, 0, 0)
        return empty, pd.DataFrame()

    start = frame["trade_date"].min()
    end = frame["trade_date"].max()
    if calendar.empty:
        sessions = pd.DatetimeIndex(sorted(frame["trade_date"].unique()))
    else:
        calendar_dates = pd.to_datetime(calendar["cal_date"]).dt.normalize()
        sessions = pd.DatetimeIndex(calendar_dates[calendar_dates.between(start, end)].unique())
    expected_per_symbol = len(sessions)
    expected_rows = expected_per_symbol * len(selected_symbols)
    unique_rows = int(frame.drop_duplicates(["symbol", "trade_date"]).shape[0])
    missing_rows = max(expected_rows - unique_rows, 0)
    duplicate_rows = int(frame.duplicated(["symbol", "trade_date"]).sum())
    quality = (
        frame["quality_status"].astype(str)
        if "quality_status" in frame.columns
        else pd.Series("OK", index=frame.index)
    )
    unknown_rows = int(quality.ne("OK").sum())
    missing_prices = int(
        frame.reindex(columns=["raw_open", "raw_close"]).isna().any(axis=1).sum()
    )

    per_symbol_rows: list[dict[str, Any]] = []
    for symbol in selected_symbols:
        group = frame[frame["symbol"].eq(symbol)]
        rows = int(group.drop_duplicates("trade_date").shape[0])
        symbol_quality = (
            group["quality_status"].astype(str)
            if "quality_status" in group.columns
            else pd.Series("OK", index=group.index)
        )
        per_symbol_rows.append(
            {
                "symbol": symbol,
                "rows": rows,
                "start_date": group["trade_date"].min().date() if not group.empty else None,
                "end_date": group["trade_date"].max().date() if not group.empty else None,
                "expected_rows": expected_per_symbol,
                "missing_rows": max(expected_per_symbol - rows, 0),
                "coverage_ratio": (
                    rows / expected_per_symbol if expected_per_symbol else 0.0
                ),
                "unknown_status_rows": int(symbol_quality.ne("OK").sum()),
            }
        )

    coverage = DatasetCoverage(
        rows=len(frame),
        symbol_count=len(selected_symbols),
        start_date=start.date(),
        end_date=end.date(),
        expected_rows=expected_rows,
        missing_rows=missing_rows,
        coverage_ratio=unique_rows / expected_rows if expected_rows else 0.0,
        duplicate_rows=duplicate_rows,
        unknown_status_rows=unknown_rows,
        missing_price_rows=missing_prices,
    )
    return coverage, pd.DataFrame(per_symbol_rows)
