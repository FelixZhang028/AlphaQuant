"""Read-only first-run and local-data readiness checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pandas as pd

from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.data_service import DataCenterService
from quant_platform.application.universe_service import UniverseManagementService


class ReadinessStatus(StrEnum):
    """Chinese UI severity for one setup check."""

    READY = "已完成"
    WARNING = "建议处理"
    ACTION = "需要处理"


@dataclass(frozen=True)
class ReadinessCheck:
    """One actionable first-run check."""

    item: str
    status: ReadinessStatus
    detail: str
    destination: str | None = None


@dataclass(frozen=True)
class ReadinessReport:
    """Complete local-platform readiness result."""

    checks: tuple[ReadinessCheck, ...]
    ready_for_backtest: bool
    configured_symbols: int
    symbols_with_sufficient_history: int
    required_history_rows: int

    def to_frame(self) -> pd.DataFrame:
        """Return a Chinese display table."""

        icons = {
            ReadinessStatus.READY: "✅",
            ReadinessStatus.WARNING: "⚠️",
            ReadinessStatus.ACTION: "❌",
        }
        return pd.DataFrame(
            [
                {
                    "检查项目": check.item,
                    "状态": f"{icons[check.status]} {check.status.value}",
                    "说明": check.detail,
                }
                for check in self.checks
            ]
        )


class PlatformReadinessService:
    """Inspect configuration and local datasets without accessing the network."""

    def __init__(self, app_config_path: str | Path = "configs/app.yaml") -> None:
        self.app_config_path = Path(app_config_path)

    def inspect(self) -> ReadinessReport:
        """Build a setup checklist and decide whether a backtest can be attempted."""

        checks: list[ReadinessCheck] = []
        try:
            backtests = BacktestService(self.app_config_path)
            backtests.default_request()
            checks.append(
                ReadinessCheck("应用配置", ReadinessStatus.READY, "配置和默认策略可以正常加载")
            )
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    "应用配置",
                    ReadinessStatus.ACTION,
                    f"配置无法加载：{exc}",
                )
            )
            return ReadinessReport(tuple(checks), False, 0, 0, 0)

        try:
            universe_service = UniverseManagementService(self.app_config_path)
            settings = universe_service.load()
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    "股票池",
                    ReadinessStatus.ACTION,
                    f"股票池配置无法加载：{exc}",
                    "pages/5_universe_management.py",
                )
            )
            return ReadinessReport(tuple(checks), False, 0, 0, 0)

        configured_count = len(settings.symbols)
        required_rows = max(settings.minimum_history_days, 2)
        if configured_count:
            checks.append(
                ReadinessCheck(
                    "股票池",
                    ReadinessStatus.READY,
                    f"已配置 {configured_count} 只股票",
                    "pages/5_universe_management.py",
                )
            )
        else:
            checks.append(
                ReadinessCheck(
                    "股票池",
                    ReadinessStatus.ACTION,
                    "尚未添加股票",
                    "pages/5_universe_management.py",
                )
            )

        try:
            overview = DataCenterService(self.app_config_path).overview()
        except Exception as exc:
            checks.append(
                ReadinessCheck(
                    "本地数据",
                    ReadinessStatus.ACTION,
                    f"本地数据无法读取：{exc}",
                    "pages/1_data_management.py",
                )
            )
            return ReadinessReport(tuple(checks), False, configured_count, 0, required_rows)

        checks.append(
            ReadinessCheck(
                "证券主表",
                ReadinessStatus.READY if overview.security_count else ReadinessStatus.WARNING,
                (
                    f"已有 {overview.security_count:,} 只证券的名称和上市信息"
                    if overview.security_count
                    else "尚未下载证券主表；不影响代码方式添加股票，但不能按名称搜索"
                ),
                "pages/1_data_management.py",
            )
        )

        sufficient = 0
        if not overview.per_symbol.empty and "rows" in overview.per_symbol.columns:
            rows = pd.to_numeric(overview.per_symbol["rows"], errors="coerce").fillna(0)
            sufficient = int(rows.ge(required_rows).sum())
        if overview.market.rows == 0:
            market_status = ReadinessStatus.ACTION
            market_detail = "尚无股票日线行情，请先更新配置股票池行情"
        elif sufficient == 0:
            market_status = ReadinessStatus.ACTION
            market_detail = f"已有行情，但没有股票达到至少 {required_rows} 个交易日"
        elif sufficient < configured_count:
            market_status = ReadinessStatus.WARNING
            market_detail = (
                f"{sufficient}/{configured_count} 只股票达到至少 {required_rows} 个交易日，"
                "可以回测，但部分股票会被过滤"
            )
        else:
            market_status = ReadinessStatus.READY
            market_detail = (
                f"{configured_count} 只股票均达到至少 {required_rows} 个交易日，"
                f"整体覆盖率 {overview.market.coverage_ratio:.1%}"
            )
        checks.append(
            ReadinessCheck(
                "股票行情",
                market_status,
                market_detail,
                "pages/1_data_management.py",
            )
        )

        benchmark_ready = overview.benchmark.rows > 0
        checks.append(
            ReadinessCheck(
                "基准行情",
                ReadinessStatus.READY if benchmark_ready else ReadinessStatus.WARNING,
                (
                    f"已准备基准 {overview.benchmark_symbol}"
                    if benchmark_ready
                    else f"尚未准备基准 {overview.benchmark_symbol}；当前仍可运行策略回测"
                ),
                "pages/1_data_management.py",
            )
        )

        quality_issues = overview.market.duplicate_rows + overview.market.missing_price_rows
        checks.append(
            ReadinessCheck(
                "数据质量",
                ReadinessStatus.READY if quality_issues == 0 else ReadinessStatus.WARNING,
                (
                    "未发现重复行情或关键价格缺失"
                    if quality_issues == 0
                    else (
                        f"发现重复 {overview.market.duplicate_rows} 行、"
                        f"关键价格缺失 {overview.market.missing_price_rows} 行"
                    )
                ),
                "pages/1_data_management.py",
            )
        )

        ready = configured_count > 0 and sufficient > 0
        return ReadinessReport(
            tuple(checks),
            ready,
            configured_count,
            sufficient,
            required_rows,
        )


def platform_needs_onboarding(app_config_path: str | Path = "configs/app.yaml") -> bool:
    """Return whether navigation should open on the first-use guide.

    This lightweight navigation check reads only symbol and date columns. The
    detailed guide performs the full coverage and quality inspection.
    """

    try:
        BacktestService(app_config_path).default_request()
        universe_service = UniverseManagementService(app_config_path)
        settings = universe_service.load()
        if not settings.symbols:
            return True
        path = universe_service.repository.root / "daily_bars.parquet"
        if not path.exists():
            return True
        bars = pd.read_parquet(path, columns=["symbol", "trade_date"])
        selected = bars[bars["symbol"].isin(settings.symbols)]
        required_rows = max(settings.minimum_history_days, 2)
        counts = selected.groupby("symbol", observed=True)["trade_date"].nunique()
        return not bool(counts.ge(required_rows).any())
    except Exception:
        return True
