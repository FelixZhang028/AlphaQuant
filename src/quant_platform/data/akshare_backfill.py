"""Efficient AkShare-only range backfill for the initial A-share universe."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import normalize_akshare_daily
from quant_platform.data.quality import DataQualityReport, inspect_daily_bars
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository

logger = logging.getLogger(__name__)


class AkShareRangeBackfill:
    """Download raw and qfq bars once per symbol, then publish canonical data."""

    def __init__(
        self,
        raw_repository: RawDataRepository,
        market_repository: ParquetMarketDataRepository,
        client: Any | None = None,
        retries: int = 3,
    ) -> None:
        if client is None:
            import akshare as ak

            client = ak
        self.client = client
        self.raw_repository = raw_repository
        self.market_repository = market_repository
        self.retries = retries

    def backfill(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> DataQualityReport:
        """Backfill a fixed universe without requiring a Tushare token."""

        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            frame = self._fetch_symbol(symbol, start_date, end_date)
            if not frame.empty:
                frames.append(frame)
        if not frames:
            raise DataUnavailableError("AkShare returned no bars for the requested universe")

        daily = pd.concat(frames, ignore_index=True).sort_values(["trade_date", "symbol"])
        calendar = pd.DataFrame(
            {
                "cal_date": sorted(daily["trade_date"].dropna().unique()),
                "is_open": 1,
                "exchange": "CN",
                "source": "akshare_bar_union",
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

    def _fetch_symbol(self, symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
        code = symbol.split(".")[0]
        parameters = {
            "symbol": code,
            "period": "daily",
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
        }
        raw = self._request(**parameters, adjust="")
        qfq = self._request(**parameters, adjust="qfq")
        self.raw_repository.save(
            "akshare",
            "daily_range_raw",
            end_date,
            raw,
            {**parameters, "adjust": ""},
        )
        self.raw_repository.save(
            "akshare",
            "daily_range_qfq",
            end_date,
            qfq,
            {**parameters, "adjust": "qfq"},
        )
        if raw.empty or qfq.empty:
            logger.warning("AkShare returned incomplete data for %s", symbol)
            return pd.DataFrame()

        bars = normalize_akshare_daily(raw)
        adjusted = qfq.rename(
            columns={
                "日期": "trade_date",
                "股票代码": "source_symbol",
                "收盘": "adjusted_close",
            }
        ).copy()
        adjusted["trade_date"] = pd.to_datetime(adjusted["trade_date"]).dt.normalize()
        adjusted = adjusted[["trade_date", "adjusted_close"]].drop_duplicates("trade_date")
        bars = bars.merge(adjusted, on="trade_date", how="left")
        bars["symbol"] = symbol
        bars["adj_factor"] = pd.to_numeric(bars["adjusted_close"], errors="coerce") / pd.to_numeric(
            bars["raw_close"], errors="coerce"
        )
        bars["up_limit"] = pd.NA
        bars["down_limit"] = pd.NA
        bars["is_suspended"] = False
        bars["is_st"] = False
        bars["is_listed"] = True
        bars["quality_status"] = "UNKNOWN_STATUS"
        missing_adjusted = bars["adjusted_close"].isna()
        bars.loc[missing_adjusted, "quality_status"] = "MISSING_ADJ_FACTOR"
        return bars

    def _request(self, **parameters: Any) -> pd.DataFrame:
        failures: list[str] = []
        for attempt in range(1, self.retries + 1):
            try:
                return self.client.stock_zh_a_hist(**parameters)
            except Exception as exc:
                failures.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
                if attempt < self.retries:
                    time.sleep(min(attempt, 2))
        raise DataUnavailableError("AkShare request failed; " + "; ".join(failures))
