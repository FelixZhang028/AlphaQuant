"""Range backfill using iFinD history quotes."""

from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import normalize_ifind_daily
from quant_platform.data.providers.ifind_provider import IFindDataProvider
from quant_platform.data.quality import DataQualityReport, inspect_daily_bars
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository


class IFindRangeBackfill:
    """Download raw and forward-adjusted iFinD bars and publish canonical data."""

    def __init__(
        self,
        raw_repository: RawDataRepository,
        market_repository: ParquetMarketDataRepository,
        provider: IFindDataProvider,
    ) -> None:
        self.raw_repository = raw_repository
        self.market_repository = market_repository
        self.provider = provider

    def backfill(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> DataQualityReport:
        request = {
            "symbols": symbols,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        raw = self.provider.get_history_range(symbols, start_date, end_date, cps=1)
        adjusted_raw = self.provider.get_history_range(symbols, start_date, end_date, cps=2)
        self.raw_repository.save(
            "ifind", "daily_range_raw", end_date, raw, {**request, "CPS": 1}
        )
        self.raw_repository.save(
            "ifind", "daily_range_qfq", end_date, adjusted_raw, {**request, "CPS": 2}
        )
        if raw.empty or adjusted_raw.empty:
            raise DataUnavailableError("iFinD returned incomplete history for the requested range")

        bars = normalize_ifind_daily(raw)
        adjusted = normalize_ifind_daily(adjusted_raw)[
            ["symbol", "trade_date", "raw_close"]
        ].rename(columns={"raw_close": "adjusted_close"})
        keys = ["symbol", "trade_date"]
        daily = bars.merge(adjusted, on=keys, how="left")
        denominator = pd.to_numeric(daily["raw_close"], errors="coerce").replace(0, pd.NA)
        daily["adj_factor"] = pd.to_numeric(
            daily["adjusted_close"], errors="coerce"
        ) / denominator
        daily["up_limit"] = pd.NA
        daily["down_limit"] = pd.NA
        daily["is_suspended"] = False
        daily["is_st"] = False
        daily["is_listed"] = True
        daily["quality_status"] = "UNKNOWN_STATUS"
        daily.loc[daily["adjusted_close"].isna(), "quality_status"] = "MISSING_ADJ_FACTOR"
        daily = daily.sort_values(["trade_date", "symbol"]).reset_index(drop=True)

        calendar = pd.DataFrame(
            {
                "cal_date": sorted(daily["trade_date"].dropna().unique()),
                "is_open": 1,
                "exchange": "CN",
                "source": "ifind_bar_union",
            }
        )
        master = pd.DataFrame(
            {
                "symbol": symbols,
                "name": symbols,
                "exchange": [symbol.split(".")[-1] for symbol in symbols],
                "list_status": "L",
            }
        )
        self.market_repository.save_table("trade_calendar", calendar)
        self.market_repository.save_table("security_master", master)
        self.market_repository.save_table("daily_bars", daily)
        return inspect_daily_bars(daily)
