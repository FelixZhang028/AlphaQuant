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

    def select(self, trade_date: date, history: pd.DataFrame) -> list[str]:
        cutoff = pd.Timestamp(trade_date)
        available = history[
            history["symbol"].isin(self.config.symbols) & (history["trade_date"] <= cutoff)
        ].sort_values(["symbol", "trade_date"])
        eligible: list[str] = []
        required_days = max(self.config.minimum_history_days, self.config.minimum_listing_days)
        for symbol, group in available.groupby("symbol", observed=True):
            if len(group) < required_days:
                continue
            latest = group.iloc[-1]
            if pd.Timestamp(latest["trade_date"]) != cutoff:
                continue
            if str(latest.get("quality_status", "OK")) not in {"OK", "UNKNOWN_STATUS"}:
                continue
            if self.config.exclude_suspended and bool(latest.get("is_suspended", False)):
                continue
            if self.config.exclude_st and bool(latest.get("is_st", False)):
                continue
            if not bool(latest.get("is_listed", True)):
                continue
            average_amount = pd.to_numeric(group.tail(20)["amount"], errors="coerce").mean()
            if average_amount < self.config.minimum_average_amount:
                continue
            eligible.append(str(symbol))
        return sorted(eligible)
