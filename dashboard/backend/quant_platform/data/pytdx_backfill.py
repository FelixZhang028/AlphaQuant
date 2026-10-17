"""Gap-only daily-bar backfill using optional PyTDX quote servers."""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import normalize_pytdx_daily
from quant_platform.data.providers.pytdx_provider import PyTdxDataProvider
from quant_platform.data.quality import DataQualityReport, inspect_daily_bars
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository

logger = logging.getLogger(__name__)


class PyTdxRangeBackfill:
    """Fill missing SH/SZ daily bars without replacing existing canonical rows."""

    def __init__(
        self,
        raw_repository: RawDataRepository,
        market_repository: ParquetMarketDataRepository,
        provider: PyTdxDataProvider,
    ) -> None:
        self.raw_repository = raw_repository
        self.market_repository = market_repository
        self.provider = provider
        self.metadata: dict[str, int | str] = {}

    def backfill(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> DataQualityReport:
        frames: list[pd.DataFrame] = []
        servers: list[str] = []
        page_count = 0
        received_rows = 0
        publish_end_date = min(end_date, date.today() - timedelta(days=1))

        for symbol in symbols:
            raw = self.provider.get_history_range(symbol, start_date, end_date)
            metrics = self.provider.last_metrics
            request: dict[str, object] = {
                "symbol": symbol,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            }
            if metrics is not None:
                request.update(
                    {
                        "server": metrics.server,
                        "page_count": metrics.page_count,
                        "received_rows": metrics.received_rows,
                    }
                )
                servers.append(metrics.server)
                page_count += metrics.page_count
                received_rows += metrics.received_rows
            self.raw_repository.save("pytdx", "daily_range_raw", end_date, raw, request)

            bars = normalize_pytdx_daily(raw, symbol)
            bars = bars[
                bars["trade_date"].between(
                    pd.Timestamp(start_date), pd.Timestamp(publish_end_date)
                )
            ].copy()
            if bars.empty:
                logger.warning("PyTDX returned no in-range bars for %s", symbol)
                continue
            for column in ("adjusted_close", "adj_factor", "up_limit", "down_limit"):
                bars[column] = float("nan")
            for column in ("is_suspended", "is_st", "is_listed"):
                bars[column] = pd.Series(pd.NA, index=bars.index, dtype="boolean")
            bars["status_source"] = "pytdx:unavailable"
            bars["adjustment_source"] = "pytdx:unavailable"
            bars["quality_status"] = "MISSING_ADJ_FACTOR"
            missing_price = bars[["raw_open", "raw_close", "pre_close"]].isna().any(axis=1)
            bars.loc[missing_price, "quality_status"] = "MISSING_PRICE"
            frames.append(bars)

        if not frames:
            raise DataUnavailableError("PyTDX returned no bars for the requested universe")

        daily = (
            pd.concat(frames, ignore_index=True)
            .drop_duplicates(["symbol", "trade_date"], keep="last")
            .sort_values(["trade_date", "symbol"])
            .reset_index(drop=True)
        )
        report = inspect_daily_bars(daily)
        incoming = self._missing_only(daily, symbols, start_date, end_date)
        if not incoming.empty:
            self._save_missing_calendar(incoming)
            self.market_repository.save_table("daily_bars", incoming)

        self.metadata = {
            "server": ",".join(dict.fromkeys(servers)),
            "page_count": page_count,
            "received_rows": received_rows,
            "candidate_rows": len(daily),
            "inserted_rows": len(incoming),
            "skipped_existing_rows": len(daily) - len(incoming),
        }
        return report

    def _missing_only(
        self,
        daily: pd.DataFrame,
        symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        existing = self.market_repository.get_daily_bars(symbols, start_date, end_date)
        keys = ["symbol", "trade_date"]
        if existing.empty or not set(keys).issubset(existing.columns):
            return daily
        existing_keys = existing[keys].drop_duplicates()
        merged = daily.merge(existing_keys.assign(_exists=True), on=keys, how="left")
        return merged[merged["_exists"].isna()].drop(columns="_exists")

    def _save_missing_calendar(self, bars: pd.DataFrame) -> None:
        dates = pd.Series(pd.to_datetime(bars["trade_date"]).dt.normalize().unique())
        existing = self.market_repository.read_table("trade_calendar")
        if not existing.empty and "cal_date" in existing.columns:
            known = set(pd.to_datetime(existing["cal_date"]).dt.normalize())
            dates = dates[~dates.isin(known)]
        if dates.empty:
            return
        calendar = pd.DataFrame(
            {
                "cal_date": sorted(dates),
                "is_open": 1,
                "exchange": "CN",
                "source": "pytdx_bar_union",
            }
        )
        self.market_repository.save_table("trade_calendar", calendar)
