"""Validity checks and plain-language trust labels for backtest results."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd

CURRENT_AUDIT_VERSION = 2
UNKNOWN_STATUS_REJECTION_REASONS = frozenset(
    {
        "UNKNOWN_MARKET_STATUS",
        "UNKNOWN_SUSPENSION_STATUS",
        "UNKNOWN_PRICE_LIMIT",
    }
)


class ValidityStatus(StrEnum):
    """Overall usability of a backtest result."""

    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"


class IssueSeverity(StrEnum):
    """Severity of one auditable validity issue."""

    WARNING = "WARNING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class ValidityIssue:
    """One machine-readable and user-readable validity finding."""

    code: str
    severity: IssueSeverity
    message: str


@dataclass(frozen=True)
class BacktestValidityReport:
    """Result of validating the time axis and research context."""

    status: ValidityStatus
    metrics_reliable: bool
    issues: tuple[ValidityIssue, ...]
    observations: int
    maximum_calendar_gap_days: int
    blocks_completion: bool
    unknown_market_rows: int = 0
    unknown_market_symbols: int = 0
    unknown_status_orders: int = 0
    audit_version: int = CURRENT_AUDIT_VERSION
    legacy_unverified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "metrics_reliable": self.metrics_reliable,
            "issues": [
                {**asdict(issue), "severity": issue.severity.value} for issue in self.issues
            ],
            "observations": self.observations,
            "maximum_calendar_gap_days": self.maximum_calendar_gap_days,
            "blocks_completion": self.blocks_completion,
            "unknown_market_rows": self.unknown_market_rows,
            "unknown_market_symbols": self.unknown_market_symbols,
            "unknown_status_orders": self.unknown_status_orders,
            "audit_version": self.audit_version,
            "legacy_unverified": self.legacy_unverified,
        }


def assess_backtest_validity(
    nav: pd.DataFrame,
    *,
    start_date: date,
    end_date: date,
    calendar: pd.DataFrame | None = None,
    orders: pd.DataFrame | None = None,
    unknown_market_rows: int = 0,
    unknown_market_symbols: int = 0,
    evaluation_mode: str = "in_sample",
    fixed_universe: bool = True,
    maximum_allowed_gap_days: int = 20,
    endpoint_tolerance_days: int = 15,
) -> BacktestValidityReport:
    """Validate a completed or persisted daily backtest without changing its metrics."""

    issues: list[ValidityIssue] = []
    nav_dates, nav_issues = _extract_dates(nav, "trade_date", "净值")
    issues.extend(nav_issues)
    maximum_gap = _maximum_gap(nav_dates)

    if nav_dates.empty:
        issues.append(ValidityIssue("EMPTY_NAV", IssueSeverity.ERROR, "回测没有生成净值记录。"))
    else:
        if maximum_gap > maximum_allowed_gap_days:
            issues.append(
                ValidityIssue(
                    "EXCESSIVE_DATE_GAP",
                    IssueSeverity.ERROR,
                    f"净值日期存在最长 {maximum_gap} 天的断档，绩效指标不可使用。",
                )
            )
        start_gap = abs((nav_dates.min().date() - start_date).days)
        end_gap = abs((end_date - nav_dates.max().date()).days)
        if start_gap > endpoint_tolerance_days or end_gap > endpoint_tolerance_days:
            issues.append(
                ValidityIssue(
                    "INCOMPLETE_REQUESTED_PERIOD",
                    IssueSeverity.ERROR,
                    "实际净值区间没有覆盖用户请求的回测起止范围。",
                )
            )
        if "equity" not in nav.columns:
            issues.append(
                ValidityIssue("MISSING_EQUITY", IssueSeverity.ERROR, "净值记录缺少账户权益。")
            )
        else:
            equity = pd.to_numeric(nav["equity"], errors="coerce")
            if equity.isna().any() or not equity.map(math.isfinite).all() or (equity <= 0).any():
                issues.append(
                    ValidityIssue(
                        "INVALID_EQUITY",
                        IssueSeverity.ERROR,
                        "净值中存在空值、无穷值或非正数。",
                    )
                )
            returns = equity.pct_change().dropna()
            if not returns.empty and float(returns.abs().max()) > 0.25:
                issues.append(
                    ValidityIssue(
                        "EXTREME_DAILY_RETURN",
                        IssueSeverity.WARNING,
                        "检测到绝对值超过25%的单日组合收益"
                        f"（最大 {returns.abs().max():.2%}），请复核。",
                    )
                )

    if calendar is not None:
        calendar_dates, calendar_issues = _extract_dates(calendar, "cal_date", "交易日历")
        issues.extend(calendar_issues)
        calendar_gap = _maximum_gap(calendar_dates)
        maximum_gap = max(maximum_gap, calendar_gap)
        if calendar_dates.empty:
            issues.append(
                ValidityIssue("EMPTY_CALENDAR", IssueSeverity.ERROR, "请求区间内没有交易日历。")
            )
        else:
            if calendar_gap > maximum_allowed_gap_days:
                issues.append(
                    ValidityIssue(
                        "CALENDAR_GAP",
                        IssueSeverity.ERROR,
                        f"交易日历存在最长 {calendar_gap} 天的异常断档。",
                    )
                )
            if not nav_dates.empty and set(nav_dates) != set(calendar_dates):
                issues.append(
                    ValidityIssue(
                        "NAV_CALENDAR_MISMATCH",
                        IssueSeverity.ERROR,
                        "净值日期与交易日历不一致。",
                    )
                )

    if fixed_universe:
        issues.append(
            ValidityIssue(
                "FIXED_UNIVERSE",
                IssueSeverity.WARNING,
                "本次使用当前固定股票池，结果只代表这些股票，可能存在事后选股偏差。",
            )
        )
    if evaluation_mode == "in_sample":
        issues.append(
            ValidityIssue(
                "IN_SAMPLE_ONLY",
                IssueSeverity.WARNING,
                "本次是普通历史回测，尚未经过样本外或滚动验证。",
            )
        )

    unknown_order_count = _unknown_status_order_count(orders)
    if unknown_market_rows > 0:
        issues.append(
            ValidityIssue(
                "UNKNOWN_MARKET_STATUS",
                IssueSeverity.ERROR,
                f"回测区间内有 {unknown_market_rows:,} 行行情缺少可验证的交易状态"
                f"（涉及 {unknown_market_symbols:,} 只股票），绩效指标不可用于策略评价。",
            )
        )
    if unknown_order_count > 0:
        issues.append(
            ValidityIssue(
                "UNKNOWN_STATUS_ORDERS",
                IssueSeverity.ERROR,
                f"有 {unknown_order_count:,} 笔订单因交易状态未知被拒绝，"
                "模拟组合已经受到数据缺口影响。",
            )
        )

    issues = _deduplicate_issues(issues)
    has_error = any(issue.severity == IssueSeverity.ERROR for issue in issues)
    diagnostic_issue_codes = {"UNKNOWN_MARKET_STATUS", "UNKNOWN_STATUS_ORDERS"}
    blocks_completion = any(
        issue.severity == IssueSeverity.ERROR and issue.code not in diagnostic_issue_codes
        for issue in issues
    )
    status = (
        ValidityStatus.INVALID
        if has_error
        else ValidityStatus.WARNING
        if issues
        else ValidityStatus.VALID
    )
    return BacktestValidityReport(
        status=status,
        metrics_reliable=not has_error,
        issues=tuple(issues),
        observations=len(nav_dates),
        maximum_calendar_gap_days=maximum_gap,
        blocks_completion=blocks_completion,
        unknown_market_rows=max(int(unknown_market_rows), 0),
        unknown_market_symbols=max(int(unknown_market_symbols), 0),
        unknown_status_orders=unknown_order_count,
    )


def load_persisted_validity(run_dir: str | Path) -> dict[str, Any]:
    """Load a current audit report or return a fail-closed legacy marker."""

    report_path = Path(run_dir) / "validity_report.json"
    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return legacy_unverified_report()
    if not isinstance(raw, dict) or raw.get("audit_version") != CURRENT_AUDIT_VERSION:
        return legacy_unverified_report()
    return {str(key): value for key, value in raw.items()}


def legacy_unverified_report() -> dict[str, Any]:
    """Describe a result that predates the current execution-safety audit."""

    return {
        "status": ValidityStatus.INVALID.value,
        "metrics_reliable": False,
        "issues": [
            {
                "code": "LEGACY_UNVERIFIED",
                "severity": IssueSeverity.ERROR.value,
                "message": "该结果未经过当前版本的交易状态审计，只能用于历史排查。",
            }
        ],
        "observations": 0,
        "maximum_calendar_gap_days": 0,
        "blocks_completion": False,
        "unknown_market_rows": 0,
        "unknown_market_symbols": 0,
        "unknown_status_orders": 0,
        "audit_version": 0,
        "legacy_unverified": True,
    }


def _unknown_status_order_count(orders: pd.DataFrame | None) -> int:
    if orders is None or orders.empty or "reject_reason" not in orders.columns:
        return 0
    reasons = orders["reject_reason"].astype("string")
    return int(reasons.isin(UNKNOWN_STATUS_REJECTION_REASONS).sum())


def _extract_dates(
    frame: pd.DataFrame, column: str, label: str
) -> tuple[pd.DatetimeIndex, list[ValidityIssue]]:
    issues: list[ValidityIssue] = []
    if frame.empty or column not in frame.columns:
        return pd.DatetimeIndex([]), issues
    converted = pd.to_datetime(frame[column], errors="coerce").dt.normalize()
    if converted.isna().any():
        issues.append(
            ValidityIssue(
                f"INVALID_{column.upper()}", IssueSeverity.ERROR, f"{label}包含无法识别的日期。"
            )
        )
    if converted.dropna().duplicated().any():
        issues.append(
            ValidityIssue(
                f"DUPLICATE_{column.upper()}", IssueSeverity.ERROR, f"{label}包含重复日期。"
            )
        )
    return pd.DatetimeIndex(sorted(converted.dropna().unique())), issues


def _maximum_gap(dates: pd.DatetimeIndex) -> int:
    if len(dates) < 2:
        return 0
    gaps = pd.Series(dates).diff().dt.days.dropna()
    return int(gaps.max()) if not gaps.empty else 0


def _deduplicate_issues(issues: list[ValidityIssue]) -> list[ValidityIssue]:
    seen: set[tuple[str, str]] = set()
    result: list[ValidityIssue] = []
    for issue in issues:
        key = (issue.code, issue.message)
        if key not in seen:
            result.append(issue)
            seen.add(key)
    return result
