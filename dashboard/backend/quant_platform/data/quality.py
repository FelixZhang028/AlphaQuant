"""Data-contract validation and quality reporting."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_platform.core.exceptions import DataQualityError


@dataclass(frozen=True)
class DataQualityReport:
    """Summary of canonical daily-bar quality."""

    rows: int
    ok_rows: int
    duplicate_rows: int
    missing_by_column: dict[str, int]
    status_counts: dict[str, int]

    @property
    def is_usable(self) -> bool:
        """Return true when the dataset has rows and no duplicate keys."""

        return self.rows > 0 and self.duplicate_rows == 0 and self.ok_rows > 0


def inspect_daily_bars(frame: pd.DataFrame) -> DataQualityReport:
    """Inspect canonical daily bars without mutating them."""

    required = {
        "symbol",
        "trade_date",
        "raw_open",
        "raw_high",
        "raw_low",
        "raw_close",
        "volume",
        "amount",
        "adj_factor",
        "quality_status",
    }
    missing_columns = sorted(required.difference(frame.columns))
    if missing_columns:
        raise DataQualityError(f"Canonical bars are missing columns: {missing_columns}")
    duplicate_rows = int(frame.duplicated(["symbol", "trade_date"]).sum())
    missing = {name: int(frame[name].isna().sum()) for name in sorted(required)}
    statuses = {
        str(key): int(value) for key, value in frame["quality_status"].value_counts().items()
    }
    return DataQualityReport(
        rows=len(frame),
        ok_rows=statuses.get("OK", 0),
        duplicate_rows=duplicate_rows,
        missing_by_column=missing,
        status_counts=statuses,
    )
