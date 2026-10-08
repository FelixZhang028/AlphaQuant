"""Daily extraction, raw snapshotting, normalization, and publication."""

from __future__ import annotations

from datetime import date

from quant_platform.data.normalizers import (
    compose_standard_daily,
    normalize_akshare_daily,
    normalize_ifind_daily,
    normalize_suspensions,
    normalize_tushare_daily,
)
from quant_platform.data.quality import DataQualityReport, inspect_daily_bars
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.data.router import DataRouter


class DailyDataPipeline:
    """Build one canonical market-data partition from routed provider calls."""

    def __init__(
        self,
        router: DataRouter,
        raw_repository: RawDataRepository,
        market_repository: ParquetMarketDataRepository,
    ) -> None:
        self.router = router
        self.raw_repository = raw_repository
        self.market_repository = market_repository

    def update(self, trade_date: date, symbols: list[str] | None = None) -> DataQualityReport:
        """Fetch, normalize, validate, and publish one trading day."""

        bars_raw, bars_source = self.router.fetch(
            "daily_bars", "get_daily_bars", trade_date=trade_date, symbols=symbols
        )
        self.raw_repository.save(
            bars_source, "daily_bars", trade_date, bars_raw, {"symbols": symbols}
        )
        normalizers = {
            "tushare": normalize_tushare_daily,
            "akshare": normalize_akshare_daily,
            "ifind": normalize_ifind_daily,
        }
        bars = normalizers[bars_source](bars_raw)

        adj, adj_source = self.router.fetch(
            "adjustment_factors",
            "get_adjustment_factors",
            trade_date=trade_date,
            symbols=symbols,
        )
        limits, limit_source = self.router.fetch(
            "price_limits", "get_price_limits", trade_date=trade_date, symbols=symbols
        )
        suspensions, suspension_source = self.router.fetch(
            "suspensions",
            "get_suspensions",
            allow_empty=True,
            trade_date=trade_date,
            symbols=symbols,
        )
        suspensions = normalize_suspensions(suspensions, suspension_source)

        for dataset, frame, source in (
            ("adjustment_factors", adj, adj_source),
            ("price_limits", limits, limit_source),
            ("suspensions", suspensions, suspension_source),
        ):
            if source != "unavailable":
                self.raw_repository.save(source, dataset, trade_date, frame, {"symbols": symbols})

        standard = compose_standard_daily(bars, adj, limits, suspensions)
        report = inspect_daily_bars(standard)
        self.market_repository.save_table("daily_bars", standard)
        return report
