"""Simple local Parquet repository with key-based upserts."""

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


class ParquetMarketDataRepository(MarketDataRepository):
    """Persist canonical market tables as local Parquet files."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.root / f"{name}.parquet"

    def save_table(self, name: str, frame: pd.DataFrame) -> None:
        """Upsert a table using its canonical natural key."""

        if frame.empty:
            return
        path = self._path(name)
        combined = (
            pd.concat([pd.read_parquet(path), frame], ignore_index=True)
            if path.exists()
            else frame.copy()
        )
        keys = _TABLE_KEYS.get(name)
        if keys and all(key in combined.columns for key in keys):
            combined = combined.drop_duplicates(keys, keep="last").sort_values(keys)
        combined.to_parquet(path, index=False)

    def read_table(self, name: str) -> pd.DataFrame:
        """Read a canonical table or return an empty frame if absent."""

        path = self._path(name)
        return pd.read_parquet(path) if path.exists() else pd.DataFrame()

    def get_daily_bars(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        frame = self.read_table("daily_bars")
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
