"""Point-in-time data access exposed to strategy implementations."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

import pandas as pd

from quant_platform.core.exceptions import DataQualityError


@dataclass(frozen=True)
class StrategyContext:
    """Read-only point-in-time view for one strategy evaluation."""

    trade_date: date
    universe: tuple[str, ...]
    _history: pd.DataFrame

    @classmethod
    def create(
        cls, trade_date: date, history: pd.DataFrame, universe: Iterable[str]
    ) -> StrategyContext:
        """Build a context that removes future and out-of-universe rows."""

        required = {"symbol", "trade_date"}
        missing = sorted(required.difference(history.columns))
        if missing:
            raise DataQualityError(f"Strategy context is missing fields: {missing}")
        symbols = tuple(sorted(set(str(symbol) for symbol in universe)))
        cutoff = pd.Timestamp(trade_date)
        available = history[
            history["symbol"].isin(symbols) & (pd.to_datetime(history["trade_date"]) <= cutoff)
        ].copy()
        available["trade_date"] = pd.to_datetime(available["trade_date"]).dt.normalize()
        return cls(
            trade_date=trade_date,
            universe=symbols,
            _history=available.sort_values(["symbol", "trade_date"]),
        )

    def require_fields(self, fields: Iterable[str]) -> None:
        """Fail before strategy execution when its data contract is unavailable."""

        missing = sorted(set(fields).difference(self._history.columns))
        if missing:
            raise DataQualityError(f"Strategy is missing required fields: {missing}")

    def history(
        self,
        fields: Iterable[str],
        lookback: int | None = None,
        symbols: Iterable[str] | None = None,
    ) -> pd.DataFrame:
        """Return a defensive copy of point-in-time history.

        ``lookback`` is applied independently to each symbol and counts rows,
        which is suitable for the current daily-frequency platform.
        """

        requested = tuple(dict.fromkeys(["symbol", "trade_date", *fields]))
        self.require_fields(requested)
        selected_symbols = (
            set(str(symbol) for symbol in symbols) if symbols is not None else set(self.universe)
        )
        frame = self._history[self._history["symbol"].isin(selected_symbols)]
        if lookback is not None:
            if lookback <= 0:
                raise ValueError("lookback must be positive")
            frame = frame.groupby("symbol", observed=True, group_keys=False).tail(lookback)
        return frame.loc[:, list(requested)].copy()
