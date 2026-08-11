"""Range backfill using BaoStock's free history and execution-status fields."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import normalize_baostock_daily
from quant_platform.data.price_limits import derive_cn_price_limits
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.quality import DataQualityReport, inspect_daily_bars
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository

logger = logging.getLogger(__name__)


class BaoStockRangeBackfill:
    """Publish canonical bars only after status and limit derivation are auditable."""

    def __init__(
        self,
        raw_repository: RawDataRepository,
        market_repository: ParquetMarketDataRepository,
        provider: BaoStockDataProvider | Any | None = None,
    ) -> None:
        self.raw_repository = raw_repository
        self.market_repository = market_repository
        self.provider = provider or BaoStockDataProvider()

    def backfill(
        self, symbols: list[str], start_date: date, end_date: date
    ) -> DataQualityReport:
        """Fetch raw/qfq bars, status fields, listing metadata, and derived limits."""

        try:
            metadata = self.provider.get_security_metadata(symbols)
            self.raw_repository.save(
                "baostock",
                "security_metadata",
                end_date,
                metadata,
                {"symbols": symbols},
            )
            master = self._normalize_master(metadata, symbols)
            frames: list[pd.DataFrame] = []
            for symbol in symbols:
                frame = self._fetch_symbol(symbol, start_date, end_date, master)
                if not frame.empty:
                    frames.append(frame)
        finally:
            self.provider.close()

        if not frames:
            raise DataUnavailableError("BaoStock returned no bars for the requested universe")

        daily = pd.concat(frames, ignore_index=True).sort_values(["trade_date", "symbol"])
        report = inspect_daily_bars(daily)
        if not report.is_usable:
            raise DataUnavailableError(
                "BaoStock data did not contain any fully verified tradable rows; "
                f"status={report.status_counts}"
            )

        calendar = pd.DataFrame(
            {
                "cal_date": sorted(daily["trade_date"].dropna().unique()),
                "is_open": 1,
                "exchange": "CN",
                "source": "baostock_bar_union",
            }
        )
        self.market_repository.save_table("trade_calendar", calendar)
        self.market_repository.save_table("security_master", master)
        self.market_repository.save_table("daily_bars", daily)
        return report

    def _fetch_symbol(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        master: pd.DataFrame,
    ) -> pd.DataFrame:
        request = {
            "symbol": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        raw = self.provider.get_history_range(
            symbol, start_date, end_date, adjustflag="3"
        )
        qfq = self.provider.get_history_range(
            symbol, start_date, end_date, adjustflag="2"
        )
        self.raw_repository.save(
            "baostock", "daily_range_raw", end_date, raw, {**request, "adjustflag": "3"}
        )
        self.raw_repository.save(
            "baostock", "daily_range_qfq", end_date, qfq, {**request, "adjustflag": "2"}
        )
        if raw.empty:
            logger.warning("BaoStock returned no raw history for %s", symbol)
            return pd.DataFrame()

        bars = normalize_baostock_daily(raw)
        if qfq.empty:
            bars["adjusted_close"] = pd.NA
        else:
            adjusted = normalize_baostock_daily(qfq)[
                ["symbol", "trade_date", "raw_close"]
            ].rename(columns={"raw_close": "adjusted_close"})
            bars = bars.merge(adjusted, on=["symbol", "trade_date"], how="left")
        denominator = pd.to_numeric(bars["raw_close"], errors="coerce").replace(0, pd.NA)
        bars["adj_factor"] = pd.to_numeric(
            bars["adjusted_close"], errors="coerce"
        ) / denominator

        metadata = master[master["symbol"].eq(symbol)]
        bars["list_date"] = metadata.iloc[0]["list_date"] if not metadata.empty else pd.NaT
        bars["delist_date"] = (
            metadata.iloc[0]["delist_date"] if not metadata.empty else pd.NaT
        )
        bars["is_listed"] = bars["list_date"].notna() & (
            bars["trade_date"] >= bars["list_date"]
        )
        bars.loc[
            bars["delist_date"].notna() & (bars["trade_date"] > bars["delist_date"]),
            "is_listed",
        ] = False
        bars = derive_cn_price_limits(bars)
        bars["status_source"] = "baostock:tradestatus,isST"
        bars["adjustment_source"] = "baostock:qfq/raw"

        missing_price = bars[["raw_open", "raw_close", "pre_close"]].isna().any(axis=1)
        missing_adjustment = bars[["adjusted_close", "adj_factor"]].isna().any(axis=1)
        unknown_status = (
            ~bars["status_known"].fillna(False)
            | ~bars["is_listed"].fillna(False)
            | bars[["up_limit", "down_limit"]].isna().any(axis=1)
        )
        bars["quality_status"] = "OK"
        bars.loc[unknown_status, "quality_status"] = "UNKNOWN_STATUS"
        bars.loc[missing_adjustment, "quality_status"] = "MISSING_ADJ_FACTOR"
        bars.loc[missing_price, "quality_status"] = "MISSING_PRICE"
        return bars.drop(columns=["status_known"])

    @staticmethod
    def _normalize_master(metadata: pd.DataFrame, symbols: list[str]) -> pd.DataFrame:
        if metadata.empty:
            return pd.DataFrame(
                {
                    "symbol": symbols,
                    "name": symbols,
                    "exchange": [symbol.split(".")[-1] for symbol in symbols],
                    "list_date": pd.NaT,
                    "delist_date": pd.NaT,
                    "list_status": "UNKNOWN",
                    "source": "baostock",
                }
            )
        result = metadata.rename(
            columns={
                "code_name": "name",
                "ipoDate": "list_date",
                "outDate": "delist_date",
            }
        ).copy()
        result["list_date"] = pd.to_datetime(result.get("list_date"), errors="coerce")
        result["delist_date"] = pd.to_datetime(result.get("delist_date"), errors="coerce")
        result["exchange"] = result["symbol"].astype(str).str.split(".").str[-1]
        current_status = result.get("status", pd.Series(index=result.index, dtype="string"))
        result["list_status"] = current_status.astype("string").map(
            {"1": "L", "0": "D"}
        ).fillna("UNKNOWN")
        result["source"] = "baostock"
        columns = [
            "symbol",
            "name",
            "exchange",
            "list_date",
            "delist_date",
            "list_status",
            "source",
        ]
        for column in columns:
            if column not in result.columns:
                result[column] = pd.NA
        return result[columns].drop_duplicates("symbol", keep="last")
