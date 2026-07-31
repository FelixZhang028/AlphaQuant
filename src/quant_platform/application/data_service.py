"""Unified data-center use cases for CLI and Streamlit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.data.akshare_backfill import AkShareRangeBackfill
from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.coverage import DatasetCoverage, calculate_daily_coverage
from quant_platform.data.network import (
    ProxyResilientAkShareClient,
    friendly_data_error,
)
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.data.versioning import DataManifest, save_manifest


@dataclass(frozen=True)
class DataUpdateResult:
    """User-facing result of one versioned dataset update."""

    dataset: str
    version_id: str
    status: str
    rows: int
    message: str
    error: str | None = None


@dataclass(frozen=True)
class DataCenterOverview:
    """Current local data state plus detailed report tables."""

    security_count: int
    configured_symbol_count: int
    benchmark_symbol: str
    market: DatasetCoverage
    benchmark: DatasetCoverage
    per_symbol: pd.DataFrame
    manifests: pd.DataFrame
    security_master: pd.DataFrame
    benchmark_bars: pd.DataFrame

    def to_dict(self) -> dict[str, Any]:
        """Return the compact section used by the JSON CLI."""

        return {
            "security_count": self.security_count,
            "configured_symbol_count": self.configured_symbol_count,
            "benchmark_symbol": self.benchmark_symbol,
            "market": self.market.to_dict(),
            "benchmark": self.benchmark.to_dict(),
        }


class DataCenterService:
    """Coordinate AkShare ingestion, version manifests, and coverage checks."""

    def __init__(
        self,
        app_config_path: str | Path = "configs/app.yaml",
        client: Any | None = None,
    ) -> None:
        self.app_config_path = Path(app_config_path)
        self.app = load_yaml(self.app_config_path)
        app_section = require_mapping(self.app, "app")
        data_section = require_mapping(self.app, "data")
        self.repository = ParquetMarketDataRepository(data_section["repository"])
        self.raw_repository = RawDataRepository(
            Path(str(app_section.get("runtime_dir", "runtime"))) / "raw"
        )
        universe_path = require_mapping(self.app, "universe")["config"]
        self.universe_config = load_yaml(universe_path)
        self.client = client
        self.direct_fallback = bool(data_section.get("direct_fallback", True))
        self._network_client: ProxyResilientAkShareClient | None = None

    @property
    def configured_symbols(self) -> list[str]:
        """Return the safe default market-data universe."""

        universe = require_mapping(self.universe_config, "universe")
        return [str(symbol) for symbol in universe.get("symbols", [])]

    @property
    def benchmark_symbol(self) -> str:
        """Return the benchmark selected in application configuration."""

        return str(require_mapping(self.app, "backtest").get("benchmark", "000300.SH"))

    def overview(self) -> DataCenterOverview:
        """Inspect local datasets without contacting external services."""

        bars = self.repository.read_table("daily_bars")
        calendar = self.repository.read_table("trade_calendar")
        market, per_symbol = calculate_daily_coverage(bars, calendar, self.configured_symbols)
        benchmark_bars = self.repository.read_table("benchmark_bars")
        if not benchmark_bars.empty:
            benchmark_bars["trade_date"] = pd.to_datetime(
                benchmark_bars["trade_date"]
            ).dt.normalize()
            benchmark_bars = benchmark_bars.drop_duplicates(
                ["symbol", "trade_date"], keep="last"
            ).sort_values("trade_date")
        benchmark, _ = calculate_daily_coverage(
            benchmark_bars,
            calendar,
            [self.benchmark_symbol],
        )
        master = self.repository.read_table("security_master")
        manifests = self.repository.read_table("data_manifests")
        if not manifests.empty:
            manifests = manifests.sort_values("completed_at", ascending=False).head(100)
        return DataCenterOverview(
            security_count=int(master["symbol"].nunique()) if not master.empty else 0,
            configured_symbol_count=len(self.configured_symbols),
            benchmark_symbol=self.benchmark_symbol,
            market=market,
            benchmark=benchmark,
            per_symbol=per_symbol,
            manifests=manifests,
            security_master=master.sort_values("symbol") if not master.empty else master,
            benchmark_bars=benchmark_bars,
        )

    def update_security_master(self) -> DataUpdateResult:
        """Refresh and version the current full A-share security list."""

        manifest = DataManifest.start("security_master", "akshare", {})
        try:
            frame = self._catalog().update_security_master()
            completed = manifest.succeed(
                row_count=len(frame), symbol_count=int(frame["symbol"].nunique())
            )
            save_manifest(self.repository, completed)
            return self._result(completed, "证券主表更新完成")
        except Exception as exc:
            save_manifest(self.repository, manifest.fail(exc))
            raise

    def update_market_data(
        self,
        start_date: date,
        end_date: date,
        symbols: list[str] | None = None,
    ) -> DataUpdateResult:
        """Refresh configured stock bars and record a reproducible version."""

        selected = symbols or self.configured_symbols
        manifest = DataManifest.start(
            "daily_bars",
            "akshare",
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "symbols": selected,
            },
        )
        existing_master = self.repository.read_table("security_master")
        try:
            report = AkShareRangeBackfill(
                self.raw_repository,
                self.repository,
                client=self._akshare_client(),
            ).backfill(selected, start_date, end_date)
            if not existing_master.empty:
                self.repository.save_table("security_master", existing_master)
            bars = self.repository.get_daily_bars(selected, start_date, end_date)
            completed = manifest.succeed(
                row_count=len(bars),
                symbol_count=int(bars["symbol"].nunique()) if not bars.empty else 0,
                min_date=(bars["trade_date"].min().date() if not bars.empty else None),
                max_date=(bars["trade_date"].max().date() if not bars.empty else None),
                quality={
                    "duplicate_rows": report.duplicate_rows,
                    "status_counts": report.status_counts,
                    "missing_by_column": report.missing_by_column,
                },
            )
            save_manifest(self.repository, completed)
            return self._result(completed, "配置股票池行情更新完成")
        except Exception as exc:
            save_manifest(self.repository, manifest.fail(exc))
            raise

    def update_benchmark(self, start_date: date, end_date: date) -> DataUpdateResult:
        """Refresh and version the configured benchmark index."""

        parameters = {
            "symbol": self.benchmark_symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        manifest = DataManifest.start("benchmark_bars", "akshare", parameters)
        try:
            frame = self._catalog().update_benchmark(self.benchmark_symbol, start_date, end_date)
            completed = manifest.succeed(
                row_count=len(frame),
                symbol_count=1,
                min_date=frame["trade_date"].min().date(),
                max_date=frame["trade_date"].max().date(),
                quality={
                    "status_counts": {
                        str(key): int(value)
                        for key, value in frame["quality_status"].value_counts().items()
                    }
                },
            )
            save_manifest(self.repository, completed)
            return self._result(completed, "基准指数更新完成")
        except Exception as exc:
            save_manifest(self.repository, manifest.fail(exc))
            raise

    def update_all(
        self,
        start_date: date,
        end_date: date,
        *,
        include_security_master: bool = True,
        include_market: bool = True,
        include_benchmark: bool = True,
    ) -> list[DataUpdateResult]:
        """Run selected updates independently in a deterministic order."""

        results: list[DataUpdateResult] = []
        if include_security_master:
            results.append(self._capture_failure("security_master", self.update_security_master))
        if include_market:
            results.append(
                self._capture_failure(
                    "daily_bars", lambda: self.update_market_data(start_date, end_date)
                )
            )
        if include_benchmark:
            results.append(
                self._capture_failure(
                    "benchmark_bars",
                    lambda: self.update_benchmark(start_date, end_date),
                )
            )
        return results

    def _catalog(self) -> AkShareCatalogIngestor:
        return AkShareCatalogIngestor(
            self.raw_repository,
            self.repository,
            client=self._akshare_client(),
        )

    def _akshare_client(self) -> ProxyResilientAkShareClient:
        if self._network_client is None:
            client = self.client
            if client is None:
                import akshare as ak

                client = ak
            self._network_client = ProxyResilientAkShareClient(
                client, direct_fallback=self.direct_fallback
            )
        return self._network_client

    def _capture_failure(
        self,
        dataset: str,
        operation: Callable[[], DataUpdateResult],
    ) -> DataUpdateResult:
        try:
            return operation()
        except Exception as exc:
            manifests = self.repository.read_table("data_manifests")
            version_id = ""
            required = {"dataset", "status", "completed_at", "version_id"}
            if not manifests.empty and required.issubset(manifests.columns):
                failed = manifests[
                    manifests["dataset"].eq(dataset) & manifests["status"].eq("FAILED")
                ]
                if not failed.empty:
                    version_id = str(failed.sort_values("completed_at").iloc[-1]["version_id"])
            return DataUpdateResult(
                dataset=dataset,
                version_id=version_id,
                status="FAILED",
                rows=0,
                message="更新失败",
                error=friendly_data_error(exc),
            )

    @staticmethod
    def _result(manifest: DataManifest, message: str) -> DataUpdateResult:
        return DataUpdateResult(
            dataset=manifest.dataset,
            version_id=manifest.version_id,
            status=manifest.status.value,
            rows=manifest.row_count,
            message=message,
            error=manifest.error,
        )
