"""Unified data-center use cases for CLI and Streamlit."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from quant_platform.application.benchmarks import BENCHMARK_NAMES
from quant_platform.application.data_jobs import serialized_update
from quant_platform.application.data_source_resolver import DataSourceResolver
from quant_platform.application.manifest_summary import add_provider_route_summary
from quant_platform.core.config import load_app_config, load_yaml, require_mapping
from quant_platform.core.exceptions import (
    DataCapabilityNotSupported,
    DataUnavailableError,
)
from quant_platform.data.akshare_backfill import AkShareRangeBackfill
from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.baostock_backfill import BaoStockRangeBackfill
from quant_platform.data.coverage import DatasetCoverage, calculate_daily_coverage
from quant_platform.data.full_market_backfill import FullMarketBackfill
from quant_platform.data.ifind_backfill import IFindRangeBackfill
from quant_platform.data.network import (
    ProxyResilientAkShareClient,
    friendly_data_error,
)
from quant_platform.data.pytdx_backfill import PyTdxRangeBackfill
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.data.versioning import DataManifest, save_manifest
from quant_platform.data.xtick_backfill import XTickRangeBackfill

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
    symbol: str | None = None


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
        pytdx_client_factory: Any | None = None,
    ) -> None:
        self.app_config_path = Path(app_config_path).resolve()
        self.app = load_app_config(self.app_config_path)
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
        self.sources = DataSourceResolver(
            self.app_config_path,
            self.source_config,
            ifind_client=self.ifind_client,
            baostock_client=self.baostock_client,
            pytdx_client_factory=pytdx_client_factory,
        )
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

    @property
    def benchmark_name(self) -> str:
        """Return the human-readable benchmark name."""
        backtest = require_mapping(self.app, "backtest")
        return str(
            backtest.get(
                "benchmark_name", BENCHMARK_NAMES.get(self.benchmark_symbol, self.benchmark_symbol)
            )
        )

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
            manifests = add_provider_route_summary(manifests)
        return DataCenterOverview(
            security_count=int(master["symbol"].nunique()) if not master.empty else 0,
            configured_symbol_count=len(self.configured_symbols),
            benchmark_symbol=self.benchmark_symbol,
            market=market,
            benchmark=benchmark,
            per_symbol=per_symbol,
            manifests=manifests,
            security_master=(master.sort_values("symbol") if not master.empty else master),
            benchmark_bars=benchmark_bars,
        )

    def market_source_status(self) -> pd.DataFrame:
        """Return configuration readiness without contacting external providers."""

        self.sources.load_local_environment()
        rows: list[dict[str, Any]] = []
        for index, source in enumerate(self.sources.market_sources()):
            provider_config = self.source_config.get("providers", {}).get(source, {})
            display_name = str(provider_config.get("display_name", source))
            if source == "xtick":
                token_env = str(provider_config.get("token_env", "XTICK_TOKEN"))
                ready = bool(os.getenv(token_env))
                detail = (
                    "Token 已配置；当前仅支持 XTick 专项查询，批量回测更新尚未接入"
                    if ready
                    else f"未配置 {token_env}；当前路由会自动回退"
                )
            elif source == "baostock":
                ready = self.baostock_client is not None or self.sources.sdk_ready("baostock")
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
                sdk_ready = self.sources.sdk_ready("iFinDPy")
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
            elif source == "pytdx":
                ready = self.sources.pytdx_client_factory is not None or self.sources.sdk_ready(
                    "pytdx"
                )
                detail = (
                    "通达信日线缺口补充来源；不会覆盖已有行情"
                    if ready
                    else "未安装 PyTDX；更新时将跳过并报告失败"
                )
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
        """Backward-compatible wrapper around the extracted helper."""

        return add_provider_route_summary(manifests)

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
        sources = self.sources.resolve_market_sources(source_order)
        fallback_enabled = self.sources.fallback_enabled(allow_fallback)
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
                f"行情更新完成（来源：{self.sources.source_display_name(source)}）",
            )
        except Exception as exc:
            failed = DataManifest.start("daily_bars", " -> ".join(sources), parameters).fail(exc)
            save_manifest(self.repository, failed)
            raise

    def update_corporate_actions(
        self,
        start_date: date,
        end_date: date,
        symbols: list[str] | None = None,
    ) -> DataUpdateResult:
        """Refresh dividend and bonus entitlements for the configured universe.

        分红送配明细是回测引擎现金结算的必需数据：复权因子变化的交易日
        若缺少对应明细，回测会被有效性检查阻断。
        """

        selected = symbols or self.configured_symbols
        parameters: dict[str, Any] = {
            "symbols": selected,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        manifest = DataManifest.start("corporate_actions", "akshare", parameters)
        try:
            frame, failures = self._catalog().update_corporate_actions(selected)
            quality: dict[str, Any] = {"failed_symbols": failures}
            if not frame.empty:
                quality["cash_records"] = int(frame["cash_per_share"].gt(0).sum())
                quality["bonus_records"] = int(frame["share_multiplier"].ne(1.0).sum())
            completed = manifest.succeed(
                row_count=len(frame),
                symbol_count=int(frame["symbol"].nunique()) if not frame.empty else 0,
                min_date=(frame["ex_date"].min().date() if not frame.empty else None),
                max_date=(frame["ex_date"].max().date() if not frame.empty else None),
                quality=quality,
            )
            save_manifest(self.repository, completed)
            message = "分红送配明细更新完成"
            if failures:
                preview = ", ".join(failures[:5])
                message += f"（{len(failures)} 只获取失败：{preview}）"
            return self._result(completed, message)
        except Exception as exc:
            save_manifest(self.repository, manifest.fail(exc))
            raise

    def update_benchmark(
        self, start_date: date, end_date: date, benchmark_symbol: str | None = None
    ) -> DataUpdateResult:
        """Refresh and version the configured benchmark index."""

        symbol = benchmark_symbol or self.benchmark_symbol
        parameters = {
            "symbol": symbol,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
        }
        manifest = DataManifest.start("benchmark_bars", "akshare", parameters)
        try:
            if self.client is None and os.getenv("XTICK_TOKEN"):
                frame = XTickRangeBackfill(self.raw_repository, self.repository).benchmark(
                    symbol, start_date, end_date
                )
                existing = self.repository.read_table("benchmark_bars")
                frame = pd.concat([existing, frame], ignore_index=True).drop_duplicates(
                    ["symbol", "trade_date"], keep="last"
                )
                self.repository.save_table("benchmark_bars", frame)
            else:
                frame = self._catalog().update_benchmark(symbol, start_date, end_date)
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

    @serialized_update
    def update_all(
        self,
        start_date: date,
        end_date: date,
        *,
        include_security_master: bool = True,
        include_market: bool = True,
        include_corporate_actions: bool = True,
        include_benchmark: bool = True,
        market_source_order: list[str] | None = None,
        allow_market_fallback: bool | None = None,
        benchmark_symbol: str | None = None,
        benchmark_symbols: list[str] | None = None,
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
        if include_corporate_actions:
            results.append(
                self._capture_failure(
                    "corporate_actions",
                    lambda: self.update_corporate_actions(start_date, end_date),
                )
            )
        if include_benchmark:
            symbols = benchmark_symbols or (
                [benchmark_symbol] if benchmark_symbol else [self.benchmark_symbol]
            )
            for symbol in symbols:
                results.append(
                    replace(
                        self._capture_failure(
                            "benchmark_bars",
                            lambda symbol=symbol: self.update_benchmark(
                                start_date, end_date, symbol
                            ),
                        ),
                        symbol=symbol,
                    )
                )
        return results

    def full_market_backfill(self) -> FullMarketBackfill:
        """构造全市场闭环回填器，与数据中心共享仓库和网络客户端。"""

        runtime_dir = require_mapping(self.app, "app").get("runtime_dir", "runtime")
        return FullMarketBackfill(
            self.raw_repository,
            self.repository,
            self.sources.baostock_provider(),
            akshare_client=self._akshare_client(),
            state_path=Path(str(runtime_dir)) / "full_market_backfill_state.json",
        )

    @serialized_update
    def run_closed_loop(
        self,
        start_date: date,
        end_date: date,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """执行全市场数据闭环（主表/日线/分红送配/历史成分/退市结算）。"""

        return self.full_market_backfill().run_closed_loop(start_date, end_date, **kwargs)

    def closed_loop_status(self) -> dict[str, Any]:
        """只读汇总闭环五张表的落地情况与断点进度（不访问外网）。"""

        master = self.repository.read_table("security_master")
        bars = self.repository.read_table("daily_bars")
        membership = self.repository.read_table("universe_membership")
        settlements = self.repository.read_table("delisting_settlements")
        actions = self.repository.read_table("corporate_actions")
        bars_symbols = int(bars["symbol"].nunique()) if not bars.empty else 0
        status: dict[str, Any] = {
            "master_total": int(len(master)) if not master.empty else 0,
            "master_delisted": (
                int(master["delist_date"].notna().sum())
                if not master.empty and "delist_date" in master.columns
                else 0
            ),
            "bars_symbols": bars_symbols,
            "bars_rows": int(len(bars)),
            "bars_min": (
                bars["trade_date"].min().date().isoformat() if bars_symbols else None
            ),
            "bars_max": (
                bars["trade_date"].max().date().isoformat() if bars_symbols else None
            ),
            "membership_rows": int(len(membership)) if not membership.empty else 0,
            "membership_symbols": (
                int(membership["symbol"].nunique()) if not membership.empty else 0
            ),
            "settlement_rows": int(len(settlements)) if not settlements.empty else 0,
            "corporate_action_rows": int(len(actions)) if not actions.empty else 0,
        }
        runtime_dir = require_mapping(self.app, "app").get("runtime_dir", "runtime")
        state_path = Path(str(runtime_dir)) / "full_market_backfill_state.json"
        backfill = FullMarketBackfill(
            self.raw_repository,
            self.repository,
            state_path=state_path,
        )
        status["checkpoint"] = backfill.state.snapshot()
        return status

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
        sources = self.sources.resolve_market_sources(source_order)
        fallback_enabled = self.sources.fallback_enabled(allow_fallback)
        for source in sources:
            try:
                if source == "baostock":
                    report = BaoStockRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        self.sources.baostock_provider(),
                    ).backfill(symbols, start_date, end_date)
                elif source == "xtick":
                    report = XTickRangeBackfill(self.raw_repository, self.repository).backfill(
                        symbols, start_date, end_date
                    )
                elif source == "ifind":
                    report = IFindRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        self.sources.ifind_provider(),
                    ).backfill(symbols, start_date, end_date)
                elif source == "akshare":
                    report = AkShareRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        client=self._akshare_client(),
                    ).backfill(symbols, start_date, end_date)
                elif source == "pytdx":
                    backfill = PyTdxRangeBackfill(
                        self.raw_repository,
                        self.repository,
                        self.sources.pytdx_provider(),
                    )
                    report = backfill.backfill(symbols, start_date, end_date)
                else:
                    raise DataCapabilityNotSupported(
                        f"Market-data source {source} has no range-backfill adapter"
                    )
                success = {"source": source, "status": "success"}
                if source == "pytdx":
                    success.update({key: str(value) for key, value in backfill.metadata.items()})
                attempts.append(success)
                return source, report, attempts
            except Exception as exc:
                from quant_platform.core.diagnostics import redact_text

                message = redact_text(f"{type(exc).__name__}: {exc}")
                attempts.append({"source": source, "status": "failed", "error": message})
                failures.append(f"{source}: {message}")
                logger.warning("Market-data provider %s failed: %s", source, message)
                if not fallback_enabled:
                    raise
        raise DataUnavailableError(
            "All configured market-data sources failed; " + "; ".join(failures)
        )

    def _resolve_market_sources(self, requested: list[str] | None) -> list[str]:
        """Backward-compatible wrapper around the extracted resolver."""

        return self.sources.resolve_market_sources(requested)

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
            error=friendly_data_error(Exception(manifest.error)) if manifest.error else None,
        )
