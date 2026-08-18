"""Local Parquet repository with key-based upserts and date partitions."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.data.interfaces import MarketDataRepository

_TABLE_KEYS: dict[str, list[str]] = {
    "daily_bars": ["symbol", "trade_date"],
    "trade_calendar": ["cal_date"],
    "security_master": ["symbol"],
}

# ``daily_bars`` is the only table that grows to millions of rows, so it is
# partitioned by calendar year. Every other canonical table stays in one file.
_PARTITIONED_TABLES = frozenset({"daily_bars"})
_PARTITION_COLUMN = "year"


class ParquetMarketDataRepository(MarketDataRepository):
    """Persist canonical market tables as local Parquet files or partitions."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _flat_path(self, name: str) -> Path:
        return self.root / f"{name}.parquet"

    def _partition_path(self, name: str) -> Path:
        return self.root / name

    def save_table(self, name: str, frame: pd.DataFrame) -> None:
        """Upsert a table using its canonical natural key."""

        if frame.empty:
            return
        if name in _PARTITIONED_TABLES:
            self._save_partitioned(name, frame)
        else:
            self._save_flat(name, frame)

    def read_table(self, name: str) -> pd.DataFrame:
        """Read a canonical table or return an empty frame if absent."""

        if name in _PARTITIONED_TABLES:
            return self._read_partitioned(name)
        return self._read_flat(name)

    def get_daily_bars(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        frame = self._read_daily_bars(start_date=start_date, end_date=end_date)
        if frame.empty:
            return frame
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
        mask = pd.Series(True, index=frame.index)
        if symbols:
            mask &= frame["symbol"].isin(symbols)
        if start_date:
            mask &= frame["trade_date"] >= pd.Timestamp(start_date)
        if end_date:
            mask &= frame["trade_date"] <= pd.Timestamp(end_date)
        return frame.loc[mask].sort_values(["trade_date", "symbol"]).reset_index(drop=True)

    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        frame = self.read_table("trade_calendar")
        if frame.empty:
            return frame
        frame["cal_date"] = pd.to_datetime(frame["cal_date"]).dt.normalize()
        mask = frame["cal_date"].between(pd.Timestamp(start_date), pd.Timestamp(end_date))
        if "is_open" in frame.columns:
            mask &= frame["is_open"].astype(int).eq(1)
        return frame.loc[mask].sort_values("cal_date").reset_index(drop=True)

    def _save_flat(self, name: str, frame: pd.DataFrame) -> None:
        path = self._flat_path(name)
        combined = (
            pd.concat([pd.read_parquet(path), frame], ignore_index=True)
            if path.exists()
            else frame.copy()
        )
        combined = self._dedupe(combined, _TABLE_KEYS.get(name))
        combined.to_parquet(path, index=False)

    def _save_partitioned(self, name: str, frame: pd.DataFrame) -> None:
        directory = self._partition_path(name)
        legacy = self._flat_path(name)
        working = frame.copy()
        working["trade_date"] = pd.to_datetime(working["trade_date"]).dt.normalize()
        working[_PARTITION_COLUMN] = working["trade_date"].dt.year

        # Migrate a legacy single-file table on the first partitioned write.
        if legacy.exists() and not self._has_partitions(directory):
            legacy_frame = pd.read_parquet(legacy)
            legacy_frame["trade_date"] = pd.to_datetime(legacy_frame["trade_date"]).dt.normalize()
            legacy_frame[_PARTITION_COLUMN] = legacy_frame["trade_date"].dt.year
            working = pd.concat([legacy_frame, working], ignore_index=True)

        keys = _TABLE_KEYS.get(name)
        for year, group in working.groupby(_PARTITION_COLUMN, observed=True):
            partition = directory / f"{_PARTITION_COLUMN}={year}"
            if self._has_partitions(partition):
                existing = self._drop_partition_column(pd.read_parquet(partition))
                group = self._drop_partition_column(group)
                group = self._dedupe(pd.concat([existing, group], ignore_index=True), keys)
            else:
                group = self._drop_partition_column(group)
                group = self._dedupe(group, keys)
            partition.mkdir(parents=True, exist_ok=True)
            group.to_parquet(partition / "data.parquet", index=False)

        if legacy.exists() and self._has_partitions(directory):
            legacy.unlink()

    def _read_flat(self, name: str) -> pd.DataFrame:
        path = self._flat_path(name)
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    def _read_partitioned(self, name: str) -> pd.DataFrame:
        directory = self._partition_path(name)
        legacy = self._flat_path(name)
        if self._has_partitions(directory):
            frame = pd.read_parquet(directory)
        elif legacy.exists():
            frame = pd.read_parquet(legacy)
        else:
            return pd.DataFrame()
        return self._drop_partition_column(frame)

    def _read_daily_bars(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> pd.DataFrame:
        directory = self._partition_path("daily_bars")
        legacy = self._flat_path("daily_bars")
        if self._has_partitions(directory):
            filters: list[tuple[str, str, int]] = []
            if start_date:
                filters.append((_PARTITION_COLUMN, ">=", start_date.year))
            if end_date:
                filters.append((_PARTITION_COLUMN, "<=", end_date.year))
            frame = (
                pd.read_parquet(directory, filters=filters)
                if filters
                else pd.read_parquet(directory)
            )
            return self._drop_partition_column(frame)
        if legacy.exists():
            return self._drop_partition_column(pd.read_parquet(legacy))
        return pd.DataFrame()

    @staticmethod
    def _has_partitions(directory: Path) -> bool:
        return directory.exists() and any(directory.iterdir())

    @staticmethod
    def _drop_partition_column(frame: pd.DataFrame) -> pd.DataFrame:
        if _PARTITION_COLUMN in frame.columns:
            return frame.drop(columns=[_PARTITION_COLUMN])
        return frame

    @staticmethod
    def _dedupe(frame: pd.DataFrame, keys: list[str] | None) -> pd.DataFrame:
        if keys and all(key in frame.columns for key in keys):
            return frame.drop_duplicates(keys, keep="last").sort_values(keys).reset_index(drop=True)
        return frame
