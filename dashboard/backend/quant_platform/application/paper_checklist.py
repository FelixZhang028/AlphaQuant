"""Pre-flight checklist for advancing a paper account toward live use."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Literal

import pandas as pd

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.user_strategies.store import UserStrategyStore

if TYPE_CHECKING:
    from quant_platform.application.paper_service import (
        PaperAccountRecord,
        PaperTradingService,
    )

Severity = Literal["blocker", "warning", "info"]

_FRESHNESS_BLOCKER_DAYS = 5
_RISK_REQUIRED_KEYS = ("max_total_weight", "max_single_weight", "max_drawdown")


@dataclass(frozen=True)
class ChecklistItem:
    """One go-live check with a user-facing verdict."""

    key: str
    title: str
    passed: bool
    severity: Severity
    detail: str


@dataclass(frozen=True)
class GoLiveChecklist:
    """Ordered checklist result for one paper account."""

    items: list[ChecklistItem]

    @property
    def blocked(self) -> bool:
        """Whether any blocker item failed."""

        return any(
            not item.passed and item.severity == "blocker" for item in self.items
        )

    def by_key(self, key: str) -> ChecklistItem:
        """Return one item by its stable key."""

        for item in self.items:
            if item.key == key:
                return item
        raise KeyError(key)


def evaluate_go_live_checklist(
    service: PaperTradingService,
    account_id: str,
    *,
    repository: ParquetMarketDataRepository | None = None,
    today: date | None = None,
) -> GoLiveChecklist:
    """Evaluate the five go-live checks for one paper account."""

    account = service.get(account_id)
    effective_today = today or date.today()
    repo = repository if repository is not None else _default_repository(service)
    items = [
        _check_data_freshness(repo, effective_today),
        _check_out_of_sample(service, account),
        _check_version_pinning(service, account),
        _check_risk_limits(account),
        _check_latest_run(service, account),
    ]
    return GoLiveChecklist(items=items)


def _default_repository(service: PaperTradingService) -> ParquetMarketDataRepository | None:
    configs = getattr(service.backtests, "configs", None)
    if not isinstance(configs, dict):
        return None
    app = configs.get("app", {})
    data = app.get("data", {}) if isinstance(app, dict) else {}
    path = data.get("repository") if isinstance(data, dict) else None
    if not path:
        return None
    return ParquetMarketDataRepository(path)


def _check_data_freshness(
    repository: ParquetMarketDataRepository | None, today: date
) -> ChecklistItem:
    key, title = "data_freshness", "行情数据是否为最新"
    if repository is None:
        return ChecklistItem(key, title, False, "blocker", "无法定位行情数据仓库。")
    try:
        bars = repository.get_daily_bars()
    except Exception as exc:  # pragma: no cover - defensive against corrupt stores
        return ChecklistItem(key, title, False, "blocker", f"读取行情数据失败：{exc}")
    if bars.empty or "trade_date" not in bars.columns:
        return ChecklistItem(key, title, False, "blocker", "行情数据仓库为空，请先更新数据。")
    latest = pd.to_datetime(bars["trade_date"]).max().date()
    calendar = repository.get_trade_calendar(latest, today)
    last_open = (
        pd.to_datetime(calendar["cal_date"]).max().date()
        if not calendar.empty and "cal_date" in calendar.columns
        else today
    )
    gap = (last_open - latest).days
    detail = (
        f"最新行情日期 {latest.isoformat()}，最近交易日 {last_open.isoformat()}，落后 {gap} 天。"
    )
    if gap > _FRESHNESS_BLOCKER_DAYS:
        return ChecklistItem(key, title, False, "blocker", detail + "请先更新行情数据。")
    if gap >= 1:
        return ChecklistItem(key, title, False, "warning", detail + "建议推进前更新数据。")
    return ChecklistItem(key, title, True, "info", detail)


def _check_out_of_sample(
    service: PaperTradingService, account: PaperAccountRecord
) -> ChecklistItem:
    key, title = "out_of_sample", "策略是否通过样本外验证"
    plugin = str(account.request.get("strategy_plugin", ""))
    try:
        records = service.backtests.run_store.list_records(successful_only=True)
    except Exception:
        records = []
    for record in records:
        if record.strategy_plugin != plugin:
            continue
        try:
            config = service.backtests.run_store.load_config(record.run_id)
            summary = service.backtests.run_store.load_summary(record.run_id)
        except Exception:
            continue
        backtest = config.get("app", {}).get("backtest", {})
        mode = backtest.get("evaluation_mode", "") if isinstance(backtest, dict) else ""
        is_oos = mode == "out_of_sample" or record.run_kind == "walk_forward_oos"
        if is_oos and bool(summary.get("metrics_reliable", False)):
            return ChecklistItem(
                key, title, True, "info", f"已找到样本外验证记录：{record.run_id}。"
            )
    return ChecklistItem(
        key, title, False, "warning", "未找到样本外验证记录，建议先完成样本外回测。"
    )


def _check_version_pinning(
    service: PaperTradingService, account: PaperAccountRecord
) -> ChecklistItem:
    key, title = "version_pinning", "参数和代码版本是否固定"
    problems: list[str] = []
    try:
        default = service.backtests.default_request()
        pinned = account.request
        for field_name, label in (
            ("strategy_parameters", "策略参数"),
            ("initial_cash", "初始资金"),
            ("top_n", "最大持仓数量"),
            ("rebalance", "调仓频率"),
        ):
            current = getattr(default, field_name)
            if pinned.get(field_name) != current:
                problems.append(f"{label}与当前默认值不一致")
        if pinned.get("risk_limits") != default.risk_limits.to_dict():
            problems.append("风控配置与当前默认值不一致")
    except Exception:
        pass
    root = getattr(service.backtests, "user_strategy_root", None)
    if root is not None:
        record = UserStrategyStore(root).get(str(account.request.get("strategy_plugin", "")))
        if record is not None:
            created_at = datetime.fromisoformat(account.created_at)
            mtime = datetime.fromtimestamp(record.code_path.stat().st_mtime, UTC)
            if mtime > created_at:
                problems.append("策略代码在账户创建后被修改")
    if problems:
        return ChecklistItem(key, title, False, "warning", "；".join(problems) + "。")
    return ChecklistItem(key, title, True, "info", "账户钉住的参数和代码版本未发生变化。")


def _check_risk_limits(account: PaperAccountRecord) -> ChecklistItem:
    key, title = "risk_limits", "仓位、回撤和风险限制是否配置"
    raw = account.request.get("risk_limits")
    if not isinstance(raw, dict) or not raw:
        return ChecklistItem(key, title, False, "blocker", "未配置任何风险限制。")
    if not bool(raw.get("enabled", False)):
        return ChecklistItem(key, title, False, "blocker", "风险限制已停用，请先启用。")
    missing = [name for name in _RISK_REQUIRED_KEYS if name not in raw]
    if missing:
        return ChecklistItem(
            key, title, False, "blocker", f"风险限制缺少关键项：{', '.join(missing)}。"
        )
    return ChecklistItem(
        key, title, True, "info", "已配置总仓位、单股权重和回撤停止线等关键限制。"
    )


def _check_latest_run(service: PaperTradingService, account: PaperAccountRecord) -> ChecklistItem:
    key, title = "latest_run", "当前运行版本与回测版本一致性"
    run_dir = service.latest_run_dir(account)
    if run_dir is None:
        return ChecklistItem(key, title, False, "blocker", "账户尚未成功运行过，无法核对版本。")
    try:
        summary = service.backtests.run_store.load_summary(run_dir.name)
    except Exception:
        try:
            raw = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            summary = raw if isinstance(raw, dict) else {}
        except Exception as exc:
            return ChecklistItem(key, title, False, "blocker", f"读取最近运行结果失败：{exc}")
    if not bool(summary.get("metrics_reliable", False)):
        return ChecklistItem(
            key, title, False, "blocker", "最近一次运行结果未通过可信度审计。"
        )
    return ChecklistItem(key, title, True, "info", f"最近运行 {run_dir.name} 结果可信。")
