"""AkShare ingestion for security reference data and benchmark indices."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.catalog_normalizers import (
    normalize_akshare_index_daily,
    normalize_akshare_security_master,
)
from quant_platform.data.interfaces import MarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository


class AkShareCatalogIngestor:
    """Download and publish non-stock-bar datasets from AkShare."""

    def __init__(
        self,
        raw_repository: RawDataRepository,
        market_repository: MarketDataRepository,
        client: Any | None = None,
    ) -> None:
        if client is None:
            import akshare as ak

            client = ak
        self.client = client
        self.raw_repository = raw_repository
        self.market_repository = market_repository

    def update_security_master(self) -> pd.DataFrame:
        """Refresh the current沪深京 A-share security list."""

        raw = pd.DataFrame(self.client.stock_info_a_code_name())
        if raw.empty:
            raise DataUnavailableError("AkShare returned an empty security master")
        captured_date = date.today()
        self.raw_repository.save("akshare", "security_master", captured_date, raw, {})
        normalized = normalize_akshare_security_master(raw)
        self.market_repository.save_table("security_master", normalized)
        return normalized

    def update_benchmark(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        """Refresh one Chinese index benchmark using a canonical symbol."""

        code = symbol.split(".", maxsplit=1)[0]
        parameters = {
            "symbol": code,
            "period": "daily",
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
        }
        raw = pd.DataFrame(self.client.index_zh_a_hist(**parameters))
        if raw.empty:
            raise DataUnavailableError(f"AkShare returned no benchmark bars: {symbol}")
        self.raw_repository.save("akshare", "benchmark_daily", end_date, raw, parameters)
        normalized = normalize_akshare_index_daily(raw, symbol)
        existing = self.market_repository.read_table("benchmark_bars")
        if not existing.empty:
            existing["trade_date"] = pd.to_datetime(existing["trade_date"]).dt.normalize()
            existing_keys = pd.MultiIndex.from_frame(existing[["symbol", "trade_date"]])
            incoming_keys = pd.MultiIndex.from_frame(normalized[["symbol", "trade_date"]])
            normalized = normalized.loc[~incoming_keys.isin(existing_keys)]
        self.market_repository.save_table("benchmark_bars", normalized)
        return normalize_akshare_index_daily(raw, symbol)
