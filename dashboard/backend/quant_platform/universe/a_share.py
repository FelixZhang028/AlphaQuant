"""Configuration-backed A-share universe and filters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from quant_platform.universe.base import Universe


@dataclass(frozen=True)
class AShareUniverseConfig:
    """Filters for the initial fixed A-share universe."""

    symbols: tuple[str, ...]
    exclude_st: bool = True
    exclude_suspended: bool = True
    minimum_listing_days: int = 0
    minimum_history_days: int = 61
    minimum_average_amount: float = 20_000_000.0


class AShareUniverse(Universe):
    """Filter a fixed symbol list using point-in-time daily state."""

    def __init__(self, config: AShareUniverseConfig) -> None:
        self.config = config
        self._eligible_by_date: dict[date, list[str]] | None = None

    def prepare(self, bars: pd.DataFrame) -> None:
        """Compute trailing filters once; no future rows influence each date."""
        frame = bars.sort_values(["symbol", "trade_date"]).copy()
        frame["history_count"] = frame.groupby("symbol").cumcount() + 1
        frame["average_amount"] = frame.groupby("symbol")["amount"].transform(
            lambda values: pd.to_numeric(values, errors="coerce").rolling(20, min_periods=1).mean()
        )
        required = max(self.config.minimum_history_days, self.config.minimum_listing_days)
        mask = frame.history_count.ge(required) & frame.average_amount.ge(
            self.config.minimum_average_amount
        )
        mask &= frame["symbol"].isin(self.symbols)
        for column, expected in (("quality_status", "OK"), ("is_listed", True)):
            mask &= frame.get(column, pd.Series(index=frame.index, dtype=object)).eq(expected)
        for column, enabled in (
            ("is_st", self.config.exclude_st),
            ("is_suspended", self.config.exclude_suspended),
        ):
            if enabled:
                mask &= frame.get(column, pd.Series(index=frame.index, dtype=object)).eq(False)
        self._eligible_by_date = {
            pd.Timestamp(day).date(): sorted(group.symbol.unique())
            for day, group in frame[mask.fillna(False)].groupby("trade_date")
        }

    @property
    def symbols(self) -> tuple[str, ...]:
        """Return the configured fixed symbol pool."""

        return self.config.symbols

    def select(self, trade_date: date, history: pd.DataFrame) -> list[str]:
        if self._eligible_by_date is not None:
            return self._eligible_by_date.get(trade_date, [])
        cutoff = pd.Timestamp(trade_date)
        available = history[
            history["symbol"].isin(self.symbols) & (history["trade_date"] <= cutoff)
        ].sort_values(["symbol", "trade_date"])
        eligible: list[str] = []
        required_days = max(self.config.minimum_history_days, self.config.minimum_listing_days)
        for symbol, group in available.groupby("symbol", observed=True):
            if len(group) < required_days:
                continue
            latest = group.iloc[-1]
            if pd.Timestamp(latest["trade_date"]) != cutoff:
                continue
            if str(latest.get("quality_status", "UNKNOWN_STATUS")) != "OK":
                continue
            suspended = latest.get("is_suspended", pd.NA)
            if self.config.exclude_suspended and (pd.isna(suspended) or bool(suspended)):
                continue
            is_st = latest.get("is_st", pd.NA)
            if self.config.exclude_st and (pd.isna(is_st) or bool(is_st)):
                continue
            is_listed = latest.get("is_listed", pd.NA)
            if pd.isna(is_listed) or not bool(is_listed):
                continue
            average_amount = pd.to_numeric(group.tail(20)["amount"], errors="coerce").mean()
            if average_amount < self.config.minimum_average_amount:
                continue
            eligible.append(str(symbol))
        return sorted(eligible)
