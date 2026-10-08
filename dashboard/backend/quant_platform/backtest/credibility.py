"""可信度审计：把引擎严谨性校验汇总为 A/B/C/D 评级与可追溯证据链。

只做测量与解读，不改动任何绩效指标。五个维度分别回答：
- 数据完整性：净值轴、交易日历与行情状态是否可验证；
- 未来函数防护：未知状态拒单、复权因子回退与公司行为校验的记录；
- 样本与选股偏差：固定股票池、样本内回测的暴露程度；
- 成本真实性：历史分期费率是否启用、费用分解与占比；
- 容量约束：参与率上限下被拒绝或削减的订单。

评级规则确定且可复核：任一维度不通过为 D；两个及以上维度有警告
为 C；单个维度有警告为 B；全部通过为 A。每条结论都携带引擎原始
检查记录作为证据，评级可以逐条追溯。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from quant_platform.backtest.validity import load_persisted_validity

# 参与率/流动性类拒单：说明订单已触及容量约束，而非数据或规则错误。
CAPACITY_REJECT_REASONS = frozenset(
    {"LIQUIDITY_LIMIT", "MISSING_LIQUIDITY", "DAILY_ORDER_LIMIT", "IMPACT_OUTSIDE_LIMIT"}
)

HEADLINES: dict[str, str] = {
    "A": "通过全部审计检查，绩效指标可用于策略评价。",
    "B": "整体可信，存在一项需要复核的警告。",
    "C": "多项审计警告叠加，结果仅作方向性参考。",
    "D": "存在错误级问题，绩效指标不可用于策略评价。",
}

DIMENSION_TITLES: dict[str, str] = {
    "data_integrity": "数据完整性",
    "lookahead_guard": "未来函数防护",
    "sample_bias": "样本与选股偏差",
    "cost_realism": "成本真实性",
    "capacity": "容量约束",
}


@dataclass(frozen=True)
class CredibilityFinding:
    """一条可追溯到引擎检查记录的审计证据。"""

    severity: str  # "info" | "warn" | "fail"
    message: str


@dataclass(frozen=True)
class CredibilityDimension:
    """一个审计维度的结论与全部证据。"""

    key: str
    title: str
    status: str  # "pass" | "warn" | "fail"
    findings: tuple[CredibilityFinding, ...]


@dataclass(frozen=True)
class CredibilityReport:
    """一次回测的可信度评级、维度结论与关键量化证据。"""

    grade: str
    headline: str
    dimensions: tuple[CredibilityDimension, ...]
    validity_status: str
    metrics_reliable: bool
    observations: int
    maximum_calendar_gap_days: int
    total_transaction_cost: float | None
    transaction_cost_ratio: float | None


def audit_credibility(
    validity: dict[str, Any],
    summary: dict[str, Any],
    execution: dict[str, Any],
    orders: pd.DataFrame,
    fills: pd.DataFrame,
    *,
    run_kind: str = "single",
) -> CredibilityReport:
    """汇总一次回测的全部审计证据并给出 A/B/C/D 评级。"""

    dimensions = [
        _dimension("data_integrity", _data_integrity_findings(validity)),
        _dimension("lookahead_guard", _lookahead_findings(validity, summary, execution)),
        _dimension("sample_bias", _sample_bias_findings(validity, summary, run_kind)),
        _dimension("cost_realism", _cost_realism_findings(summary, fills, execution)),
        _dimension("capacity", _capacity_findings(orders, execution)),
    ]
    grade = _grade(dimensions)
    total = _total_cost(summary, fills)
    initial = _number(summary, "initial_cash")
    return CredibilityReport(
        grade=grade,
        headline=HEADLINES[grade],
        dimensions=tuple(dimensions),
        validity_status=str(validity.get("status", "INVALID")),
        metrics_reliable=bool(validity.get("metrics_reliable", False)),
        observations=int(validity.get("observations") or 0),
        maximum_calendar_gap_days=int(validity.get("maximum_calendar_gap_days") or 0),
        total_transaction_cost=total,
        transaction_cost_ratio=(total / initial if total is not None and initial else None),
    )


def audit_persisted_run(run_dir: str | Path, *, run_kind: str | None = None) -> CredibilityReport:
    """读取一个持久化运行目录并生成可信度审计报告。"""

    directory = Path(run_dir)
    validity = load_persisted_validity(directory)
    summary = _read_json_mapping(directory / "summary.json")
    config = _read_yaml_mapping(directory / "config.snapshot.yaml")
    if run_kind is None:
        backtest = _nested_mapping(_nested_mapping(config, "app"), "backtest")
        run_kind = str(backtest.get("run_kind", "single"))
    return audit_credibility(
        validity,
        summary,
        _execution_settings(config),
        _read_parquet(directory / "orders.parquet"),
        _read_parquet(directory / "fills.parquet"),
        run_kind=run_kind,
    )


def _data_integrity_findings(validity: dict[str, Any]) -> list[CredibilityFinding]:
    """净值轴、日历与行情状态的可验证性；ERROR 级问题直接判不通过。"""

    findings: list[CredibilityFinding] = []
    if validity.get("legacy_unverified"):
        findings.append(
            CredibilityFinding(
                "fail", "该结果未经过当前版本的交易状态审计，只能用于历史排查。"
            )
        )
    for issue in _issues(validity):
        if str(issue.get("severity")) == "ERROR":
            findings.append(CredibilityFinding("fail", str(issue.get("message", "未知错误。"))))
    if any(finding.severity == "fail" for finding in findings):
        return findings
    observations = int(validity.get("observations") or 0)
    gap = int(validity.get("maximum_calendar_gap_days") or 0)
    findings.append(
        CredibilityFinding(
            "info",
            f"净值覆盖 {observations} 个交易日，最大日历断档 {gap} 天，"
            "净值日期与交易日历一致，未发现不可验证的行情状态。",
        )
    )
    return findings


def _lookahead_findings(
    validity: dict[str, Any], summary: dict[str, Any], execution: dict[str, Any]
) -> list[CredibilityFinding]:
    """防未来函数防线的审计：拦截记录、复权因子回退与退市结算。"""

    findings: list[CredibilityFinding] = []
    unknown_orders = int(validity.get("unknown_status_orders") or 0)
    if unknown_orders > 0:
        findings.append(
            CredibilityFinding(
                "fail",
                f"有 {unknown_orders:,} 笔订单因交易状态未知被拒绝——防线没有放行不可"
                "验证的成交，但模拟组合的构成已经受到数据缺口影响。",
            )
        )
    missing_adj = int(validity.get("missing_adj_factor_rows") or 0)
    if missing_adj > 0:
        findings.append(
            CredibilityFinding(
                "warn",
                f"有 {missing_adj:,} 次估值或成交缺少复权因子，已回退为未复权口径，"
                "除权日附近的净值可能失真。",
            )
        )
    policy = execution.get("unknown_status_policy")
    if policy == "reject_trade":
        findings.append(
            CredibilityFinding(
                "info",
                "未知状态拒单防线启用：缺行情、停牌状态未知、涨跌停未知的订单一律"
                "拒绝，不存在用未知数据虚构成交的路径。",
            )
        )
    elif policy:
        findings.append(
            CredibilityFinding("warn", f"未知状态策略为 {policy}，可能放行不可验证的成交。")
        )
    settlements = _number(summary, "delisting_settlements")
    if settlements and settlements > 0:
        findings.append(
            CredibilityFinding(
                "info", f"期内完成 {int(settlements)} 次退市结算，退市股票按结算价折算现金。"
            )
        )
    if not findings:
        findings.append(
            CredibilityFinding("info", "执行配置未记录，无法核对防未来函数防线。")
        )
    return findings


def _sample_bias_findings(
    validity: dict[str, Any], summary: dict[str, Any], run_kind: str
) -> list[CredibilityFinding]:
    """固定股票池与样本内回测的暴露度。"""

    findings: list[CredibilityFinding] = []
    codes = {str(issue.get("code")) for issue in _issues(validity)}
    if "FIXED_UNIVERSE" in codes:
        findings.append(
            CredibilityFinding(
                "warn", "使用当前固定股票池：结果只代表这些股票，可能存在事后选股偏差。"
            )
        )
    if "IN_SAMPLE_ONLY" in codes:
        findings.append(
            CredibilityFinding(
                "warn", "样本内回测：尚未经过样本外或滚动验证，过拟合风险未排除。"
            )
        )
    if not findings:
        evaluation_mode = str(summary.get("evaluation_mode", ""))
        if run_kind == "walk_forward_oos" or evaluation_mode == "out_of_sample":
            findings.append(
                CredibilityFinding(
                    "info", "样本外/滚动验证结果，参数与区间未在同一数据上重复使用。"
                )
            )
        else:
            findings.append(CredibilityFinding("info", "未检出固定股票池或样本内警告。"))
    return findings


def _cost_realism_findings(
    summary: dict[str, Any], fills: pd.DataFrame, execution: dict[str, Any]
) -> list[CredibilityFinding]:
    """费用假设的审计：历史分期费率、费用分解与占比。"""

    findings: list[CredibilityFinding] = []
    historical = execution.get("historical_fees")
    total = _total_cost(summary, fills)
    initial = _number(summary, "initial_cash")
    ratio = total / initial if total is not None and initial else None
    if historical is False:
        findings.append(
            CredibilityFinding(
                "warn", "使用固定费率模拟，未按历史分期费率扣除（如 2023-08 印花税减半）。"
            )
        )
    if ratio is not None and ratio > 0.10:
        findings.append(
            CredibilityFinding(
                "warn", f"交易成本合计占初始资金 {ratio:.1%}，成本假设对结论影响重大。"
            )
        )
    if total is not None and total > 0 and ratio is not None:
        commission = _number(summary, "commission") or _column_sum(fills, "commission")
        stamp = _number(summary, "stamp_tax") or _column_sum(fills, "stamp_tax")
        transfer = _number(summary, "transfer_fee") or _column_sum(fills, "transfer_fee")
        slippage = _number(summary, "slippage_cost") or _column_sum(fills, "slippage_cost")
        fee_label = "历史分期费率" if historical else "固定费率"
        findings.append(
            CredibilityFinding(
                "info",
                f"费用分解（{fee_label}）：佣金 {commission:,.0f} 元、印花税 {stamp:,.0f} 元、"
                f"过户费 {transfer:,.0f} 元、滑点与冲击 {slippage:,.0f} 元，"
                f"合计占初始资金 {ratio:.2%}。",
            )
        )
    elif not findings:
        findings.append(CredibilityFinding("info", "期内无成交，成本假设不影响本结果。"))
    return findings


def _capacity_findings(
    orders: pd.DataFrame, execution: dict[str, Any]
) -> list[CredibilityFinding]:
    """参与率上限下的拒单记录与容量参数。"""

    findings: list[CredibilityFinding] = []
    rejects = 0
    if orders is not None and not orders.empty and "reject_reason" in orders:
        reasons = orders["reject_reason"].astype("string").dropna()
        rejects = int(reasons.isin(CAPACITY_REJECT_REASONS).sum())
    if rejects > 0:
        findings.append(
            CredibilityFinding(
                "warn",
                f"有 {rejects:,} 笔订单被容量约束拒绝或削减——回测已计入流动性上限，"
                "策略可承载的资金规模已接近该约束。",
            )
        )
    participation = _number(execution, "max_participation")
    impact = _number(execution, "impact_coefficient")
    if participation is not None:
        message = (
            f"参与率上限 {participation:.1%}：单日订单量超过前一日成交量该比例的部分会被削减。"
        )
        if impact is not None:
            message += f"市场冲击按 sqrt(成交占比)×{impact:g} 计入成交价。"
        findings.append(CredibilityFinding("info", message))
    if not findings:
        findings.append(CredibilityFinding("info", "执行配置未记录容量参数，无法核对容量约束。"))
    return findings


def _dimension(key: str, findings: list[CredibilityFinding]) -> CredibilityDimension:
    if any(finding.severity == "fail" for finding in findings):
        status = "fail"
    elif any(finding.severity == "warn" for finding in findings):
        status = "warn"
    else:
        status = "pass"
    return CredibilityDimension(
        key=key,
        title=DIMENSION_TITLES[key],
        status=status,
        findings=tuple(findings),
    )


def _grade(dimensions: list[CredibilityDimension]) -> str:
    if any(dimension.status == "fail" for dimension in dimensions):
        return "D"
    # 按警告总数而非警告维度数：同一维度的多条警告（如固定股票池 +
    # 样本内）同样是"多项审计警告叠加"，应压低评级。
    warnings = sum(
        1
        for dimension in dimensions
        for finding in dimension.findings
        if finding.severity == "warn"
    )
    if warnings >= 2:
        return "C"
    return "B" if warnings == 1 else "A"


def _execution_settings(config: dict[str, Any]) -> dict[str, Any]:
    """提取快照中的执行参数；快照为 execution.execution 双层结构。"""

    outer = _nested_mapping(config, "execution")
    inner = _nested_mapping(outer, "execution")
    return inner if inner else outer


def _nested_mapping(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def _issues(validity: dict[str, Any]) -> list[dict[str, Any]]:
    raw = validity.get("issues", [])
    if not isinstance(raw, list):
        return []
    return [issue for issue in raw if isinstance(issue, dict)]


def _number(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _total_cost(summary: dict[str, Any], fills: pd.DataFrame) -> float | None:
    """优先取 summary 汇总，缺失时从逐笔成交明细兜底求和。"""

    total = _number(summary, "total_transaction_cost")
    if total is None and fills is not None and not fills.empty:
        total = sum(
            _column_sum(fills, column)
            for column in ("commission", "stamp_tax", "transfer_fee", "slippage_cost")
        )
    return total


def _column_sum(frame: pd.DataFrame, column: str) -> float:
    if frame is None or frame.empty or column not in frame:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0.0).sum())


def _read_json_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): value for key, value in raw.items()} if isinstance(raw, dict) else {}


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {str(key): value for key, value in raw.items()} if isinstance(raw, dict) else {}


def _read_parquet(path: Path) -> pd.DataFrame:
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError):
        return pd.DataFrame()
