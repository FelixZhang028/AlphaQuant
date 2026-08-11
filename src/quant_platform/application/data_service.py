"""Unified data-center use cases for CLI and Streamlit."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.core.config import load_yaml, require_mapping
from quant_platform.core.exceptions import DataCapabilityNotSupported, DataUnavailableError
from quant_platform.data.akshare_backfill import AkShareRangeBackfill
from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.baostock_backfill import BaoStockRangeBackfill
from quant_platform.data.coverage import DatasetCoverage, calculate_daily_coverage
from quant_platform.data.ifind_backfill import IFindRangeBackfill
from quant_platform.data.network import (
    ProxyResilientAkShareClient,
    friendly_data_error,
)
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.providers.ifind_provider import IFindDataProvider
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.data.versioning import DataManifest, save_manifest

logger = logging.getLogger(__name__)


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
        ifind_client: Any | None = None,
        baostock_client: Any | None = None,
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
        self.ifind_client = ifind_client
        self.baostock_client = baostock_client
        self.direct_fallback = bool(data_section.get("direct_fallback", True))
        source_config_path = data_section.get("source_config")
        self.source_config: dict[str, Any] = {}
        if source_config_path and Path(str(source_config_path)).exists():
            self.source_config = load_yaml(source_config_path)
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
            manifests = self._add_provider_route_summary(manifests)
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

    def market_source_status(self) -> pd.DataFrame:
        """Return configuration readiness without contacting external providers."""

        self._load_local_environment()
        rows: list[dict[str, Any]] = []
        for index, source in enumerate(self._market_sources()):
            provider_config = self.source_config.get("providers", {}).get(source, {})
            display_name = str(provider_config.get("display_name", source))
            if source == "baostock":
                try:
                    ready = (
                        self.baostock_client is not None
                        or importlib.util.find_spec("baostock") is not None
                    )
                except (ImportError, ValueError):
                    ready = self.baostock_client is not None
                detail = (
                    "免费行情、停牌和历史 ST 状态来源"
                    if ready
                    else "未安装 BaoStock；更新时将自动回退"
                )
            elif source == "ifind":
                config = provider_config
                username_env = str(config.get("username_env", "IFIND_USERNAME"))
                password_env = str(config.get("password_env", "IFIND_PASSWORD"))
                credentials_ready = bool(os.getenv(username_env) and os.getenv(password_env))
                try:
                    sdk_ready = importlib.util.find_spec("iFinDPy") is not None
                except (ImportError, ValueError):
                    sdk_ready = False
                ready = credentials_ready and sdk_ready
                if ready:
                    detail = "SDK 与账号已配置；更新时优先使用"
                elif not sdk_ready and not credentials_ready:
                    detail = "未安装 SDK，且未配置账号；将自动回退"
                elif not sdk_ready:
                    detail = "未检测到官方 SDK；将自动回退"
                else:
                    detail = "未配置账号环境变量；将自动回退"
            elif source == "akshare":
                ready = True
                detail = "公开数据备用来源"
            else:
                ready = False
                detail = "项目尚未实现此数据源"
            rows.append(
                {
                    "provider": source,
                    "display_name": display_name,
                    "role": "PRIMARY" if index == 0 else "FALLBACK",
                    "readiness": "READY" if ready else "NOT_READY",
                    "detail": detail,
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _add_provider_route_summary(manifests: pd.DataFrame) -> pd.DataFrame:
        result = manifests.copy()

        def summarize(value: object) -> tuple[str, bool, str, bool | None]:
            try:
                parameters = json.loads(str(value))
            except (json.JSONDecodeError, TypeError, ValueError):
                return "", False, "", None
            attempts = parameters.get("provider_attempts", [])
            if not isinstance(attempts, list):
                attempts = []
            labels: list[str] = []
            failed = False
            succeeded = False
            for attempt in attempts:
                if not isinstance(attempt, dict):
                    continue
                source = str(attempt.get("source", ""))
                status = str(attempt.get("status", ""))
                labels.append(f"{source}:{status}")
                failed = failed or status == "failed"
                succeeded = succeeded or status == "success"
            requested = parameters.get(
                "requested_sources", parameters.get("configured_sources", [])
            )
            requested_route = (
                " -> ".join(str(source) for source in requested)
                if isinstance(requested, list)
                else ""
            )
            fallback = parameters.get("fallback_enabled")
            fallback_enabled = fallback if isinstance(fallback, bool) else None
            return (
                " -> ".join(labels),
                failed and succeeded,
                requested_route,
                fallback_enabled,
            )

        if "parameters_json" not in result.columns:
            result["provider_route"] = ""
            result["fallback_used"] = False
            result["requested_route"] = ""
            result["fallback_enabled"] = pd.NA
            return result
        summaries = result["parameters_json"].map(summarize)
        result["provider_route"] = summaries.map(lambda item: item[0])
        result["fallback_used"] = summaries.map(lambda item: item[1])
        result["requested_route"] = summaries.map(lambda item: item[2])
        result["fallback_enabled"] = summaries.map(lambda item: item[3])
        return result

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
        *,
        source_order: list[str] | None = None,
        allow_fallback: bool | None = None,
    ) -> DataUpdateResult:
        """Refresh stock bars using a validated per-update provider order."""

        selected = symbols or self.configured_symbols
        sources = self._resolve_market_sources(source_order)
        fallback_enabled = self._fallback_enabled(allow_fallback)
        parameters: dict[str, Any] = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "symbols": selected,
            "requested_sources": sources,
            "fallback_enabled": fallback_enabled,
        }
        existing_master = self.repository.read_table("security_master")
        try:
            source, report, attempts = self._run_market_backfill(
                selected,
                start_date,
                end_date,
                source_order=sources,
                allow_fallback=fallback_enabled,
            )
            parameters["provider_attempts"] = attempts
            manifest = DataManifest.start("daily_bars", source, parameters)
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
            return self._result(
                completed,
                f"行情更新完成（来源：{self._source_display_name(source)}）",
            )
        except Exception as exc:
            failed = DataManifest.start(
                "daily_bars", " -> ".join(sources), parameters
            ).fail(exc)
            save_manifest(self.repository, failed)
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
        market_source_order: list[str] | None = None,
        allow_market_fallback: bool | None = None,
    ) -> list[DataUpdateResult]:
        """Run selected updates independently in a deterministic order."""

        results: list[DataUpdateResult] = []
        if include_security_master:
            results.append(self._capture_failure("security_master", self.update_security_master))
        if include_market:
            results.append(
                self._capture_failure(
                    "daily_bars",
                    lambda: self.update_market_data(
                        start_date,
                        end_date,
                        source_order=market_source_order,
                        allow_fallback=allow_market_fallback,
                    ),
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

    def _run_market_backfill(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        *,
        source_order: list[str] | None = None,
        allow_fallback: bool | None = None,
    ) -> tuple[str, Any, list[dict[str, str]]]:
        attempts: list[dict[str, str]] = []
        failures: list[str] = []
        sources = self._resolve_market_sources(source_order)
        fallback_enabled = self._fallback_enabled(allow_fallback)
        for source in sources:
            try:
                if source == "baostock":
                    report = BaoStockRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        self._baostock_provider(),
                    ).backfill(symbols, start_date, end_date)
                elif source == "ifind":
                    report = IFindRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        self._ifind_provider(),
                    ).backfill(symbols, start_date, end_date)
                elif source == "akshare":
                    report = AkShareRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        client=self._akshare_client(),
                    ).backfill(symbols, start_date, end_date)
                else:
                    raise DataCapabilityNotSupported(
                        f"Market-data source {source} has no range-backfill adapter"
                    )
                attempts.append({"source": source, "status": "success"})
                return source, report, attempts
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                attempts.append({"source": source, "status": "failed", "error": message})
                failures.append(f"{source}: {message}")
                logger.warning("Market-data provider %s failed: %s", source, exc)
                if not fallback_enabled:
                    raise
        raise DataUnavailableError(
            "All configured market-data sources failed; " + "; ".join(failures)
        )

    def _market_sources(self) -> list[str]:
        routing = self.source_config.get("routing", {})
        configured = routing.get("daily_bars", ["akshare"])
        providers = self.source_config.get("providers", {})
        enabled = [
            str(name)
            for name in configured
            if bool(providers.get(str(name), {}).get("enabled", True))
        ]
        return enabled or ["akshare"]

    def _source_display_name(self, source: str) -> str:
        providers = self.source_config.get("providers", {})
        config = providers.get(source, {}) if isinstance(providers, dict) else {}
        return str(config.get("display_name", source)) if isinstance(config, dict) else source

    def _resolve_market_sources(self, requested: list[str] | None) -> list[str]:
        configured = self._market_sources()
        if requested is None:
            return configured
        unique = list(dict.fromkeys(str(source).strip().lower() for source in requested))
        unique = [source for source in unique if source]
        if not unique:
            raise ValueError("At least one market-data source must be selected")
        unavailable = [source for source in unique if source not in configured]
        if unavailable:
            raise ValueError(
                "Market-data sources are disabled or not routed for daily bars: "
                + ", ".join(unavailable)
            )
        return unique

    def _fallback_enabled(self, requested: bool | None) -> bool:
        if requested is not None:
            return requested
        quality = self.source_config.get("quality", {})
        return bool(quality.get("allow_fallback_provider", True))

    def _ifind_provider(self) -> IFindDataProvider:
        self._load_local_environment()
        config = self.source_config.get("providers", {}).get("ifind", {})
        username_env = str(config.get("username_env", "IFIND_USERNAME"))
        password_env = str(config.get("password_env", "IFIND_PASSWORD"))
        username = os.getenv(username_env)
        password = os.getenv(password_env)
        if self.ifind_client is None and (not username or not password):
            raise DataUnavailableError(
                f"iFinD credentials are not configured in {username_env}/{password_env}"
            )
        return IFindDataProvider(
            username,
            password,
            client=self.ifind_client,
            batch_size=int(config.get("batch_size", 3)),
        )

    def _baostock_provider(self) -> BaoStockDataProvider:
        return BaoStockDataProvider(client=self.baostock_client)

    def _load_local_environment(self) -> None:
        candidates = [
            Path.cwd() / ".env",
            self.app_config_path.parent / ".env",
            self.app_config_path.parent.parent / ".env",
        ]
        for path in dict.fromkeys(candidates):
            if not path.is_file():
                continue
            for raw_line in path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    os.environ.setdefault(key, value)
            return

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
