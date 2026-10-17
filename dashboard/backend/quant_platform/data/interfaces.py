"""Abstract interfaces for data providers and repositories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

import pandas as pd


class DataProvider(ABC):
    """Provider interface returning source-native DataFrames."""

    name: str

    @abstractmethod
    def get_security_master(self) -> pd.DataFrame:
        """Fetch listed, delisted, and suspended securities."""

    @abstractmethod
    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Fetch the exchange calendar for a date interval."""

    @abstractmethod
    def get_daily_bars(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch source-native unadjusted bars for one trading day."""

    @abstractmethod
    def get_adjustment_factors(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch adjustment factors for one trading day."""

    @abstractmethod
    def get_price_limits(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch upper and lower price limits for one trading day."""

    @abstractmethod
    def get_suspensions(
        self,
        trade_date: date,
        symbols: list[str] | None = None,
    ) -> pd.DataFrame:
        """Fetch suspension records for one trading day."""


class MarketDataRepository(ABC):
    """Storage-neutral interface consumed by strategies and backtests."""

    @abstractmethod
    def save_table(self, name: str, frame: pd.DataFrame) -> None:
        """Upsert a canonical table."""

    @abstractmethod
    def read_table(self, name: str) -> pd.DataFrame:
        """Read a canonical table."""

    @abstractmethod
    def get_daily_bars(
        self,
        symbols: list[str] | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Read standardized daily bars for a symbol/date range."""

    @abstractmethod
    def get_trade_calendar(self, start_date: date, end_date: date) -> pd.DataFrame:
        """Read open trading dates for a date range."""
