"""Configurable target-weight risk checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from quant_platform.portfolio.models import TargetPosition
from quant_platform.risk.config import RiskLimits

RISK_WEIGHT_TOLERANCE = 0.005


class RiskDecision(StrEnum):
    """Risk evaluation result."""

    PASS = "PASS"
    ADJUST = "ADJUST"
    REJECT = "REJECT"


@dataclass(frozen=True)
class RiskEvaluation:
    """Auditable result of one target-portfolio risk check."""

    decision: RiskDecision
    reasons: tuple[str, ...]
    target_count: int
    total_weight: float
    max_weight: float
    current_drawdown: float


def validate_target_weights(targets: list[TargetPosition]) -> RiskDecision:
    """Keep the original basic validation API for existing callers."""

    if any(target.target_weight < 0 or target.target_weight > 1 for target in targets):
        return RiskDecision.REJECT
    if sum(target.target_weight for target in targets) > 1.0 + 1e-9:
        return RiskDecision.REJECT
    return RiskDecision.PASS


def evaluate_target_risk(
    targets: list[TargetPosition],
    limits: RiskLimits,
    *,
    current_drawdown: float = 0.0,
    industry_map: dict[str, str] | None = None,
) -> RiskEvaluation:
    """Apply configured portfolio limits and return all rejection reasons."""

    total_weight = sum(target.target_weight for target in targets)
    max_weight = max((target.target_weight for target in targets), default=0.0)
    reasons: list[str] = []
    if not limits.enabled:
        return RiskEvaluation(
            RiskDecision.PASS,
            (),
            len(targets),
            total_weight,
            max_weight,
            current_drawdown,
        )
    if any(target.target_weight < 0 for target in targets):
        reasons.append("目标权重不能为负数")
    if limits.max_industry_weight < 1:
        totals: dict[str, float] = {}
        for target in targets:
            industry = (industry_map or {}).get(target.symbol)
            if not industry:
                reasons.append(f"缺少历史行业：{target.symbol}")
                continue
            totals[industry] = totals.get(industry, 0) + target.target_weight
        if any(value > limits.max_industry_weight + 1e-9 for value in totals.values()):
            reasons.append("行业集中度超过限制")
    if total_weight > limits.max_total_weight + 1e-9:
        reasons.append(f"总仓位超过 {limits.max_total_weight:.0%}")
    if max_weight > limits.max_single_weight + 1e-9:
        reasons.append(f"单只股票权重超过 {limits.max_single_weight:.0%}")
    if len(targets) > limits.max_positions:
        reasons.append(f"持仓数量超过 {limits.max_positions} 只")
    if current_drawdown <= -limits.max_drawdown:
        reasons.append(f"账户回撤达到 {limits.max_drawdown:.0%} 停止线")
    return RiskEvaluation(
        RiskDecision.REJECT if reasons else RiskDecision.PASS,
        tuple(reasons),
        len(targets),
        total_weight,
        max_weight,
        current_drawdown,
    )


class PortfolioRiskAction(StrEnum):
    """Action produced by an end-of-day portfolio risk check."""

    NONE = "NONE"
    STOP_NEW = "STOP_NEW"
    REBALANCE = "REBALANCE"
    REDUCE = "REDUCE"
    LIQUIDATE = "LIQUIDATE"


@dataclass(frozen=True)
class DailyPortfolioRisk:
    """Auditable end-of-day risk decision and optional corrective targets."""

    decision: RiskDecision
    action: PortfolioRiskAction
    reasons: tuple[str, ...]
    targets: tuple[TargetPosition, ...]
    current_total_weight: float
    current_max_weight: float
    current_drawdown: float


def evaluate_daily_portfolio_risk(
    current_weights: dict[str, float],
    limits: RiskLimits,
    *,
    strategy_id: str,
    trade_date: date,
    current_drawdown: float,
    daily_return: float = 0.0,
    industry_map: dict[str, str] | None = None,
) -> DailyPortfolioRisk:
    """Check actual holdings every day and create corrective target weights."""

    clean = {symbol: max(float(weight), 0.0) for symbol, weight in current_weights.items()}
    current_total = sum(clean.values())
    current_max = max(clean.values(), default=0.0)
    if not limits.enabled:
        return DailyPortfolioRisk(
            RiskDecision.PASS,
            PortfolioRiskAction.NONE,
            (),
            (),
            current_total,
            current_max,
            current_drawdown,
        )

    adjusted = dict(clean)
    reasons: list[str] = []
    action = PortfolioRiskAction.NONE
    if daily_return <= -limits.max_daily_loss:
        return DailyPortfolioRisk(
            RiskDecision.REJECT,
            PortfolioRiskAction.STOP_NEW,
            ("单日亏损达到限制：收盘后停止生成下一交易日新委托",),
            (),
            current_total,
            current_max,
            current_drawdown,
        )
    if limits.max_industry_weight < 1:
        if any(not (industry_map or {}).get(symbol) for symbol in clean):
            return DailyPortfolioRisk(
                RiskDecision.REJECT,
                PortfolioRiskAction.STOP_NEW,
                ("持仓缺少当时可得行业，暂停新委托",),
                (),
                current_total,
                current_max,
                current_drawdown,
            )
        totals: dict[str, float] = {}
        for symbol, weight in clean.items():
            industry = industry_map[symbol]
            totals[industry] = totals.get(industry, 0) + weight
        for symbol in adjusted:
            total = totals[industry_map[symbol]]
            if total > limits.max_industry_weight:
                adjusted[symbol] *= limits.max_industry_weight / total
        if adjusted != clean:
            reasons.append("行业集中度超限，降低行业仓位")
    drawdown_breached = current_drawdown <= -limits.max_drawdown
    if drawdown_breached and limits.drawdown_action == "stop_new":
        return DailyPortfolioRisk(
            RiskDecision.REJECT,
            PortfolioRiskAction.STOP_NEW,
            (f"账户回撤达到 {limits.max_drawdown:.0%}，停止新开仓",),
            (),
            current_total,
            current_max,
            current_drawdown,
        )

    if limits.daily_position_limits:
        ranked = sorted(adjusted.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) > limits.max_positions:
            adjusted = dict(ranked[: limits.max_positions])
            reasons.append(f"实际持股数量超过 {limits.max_positions} 只，自动压缩持仓")
        if any(
            weight > limits.max_single_weight + RISK_WEIGHT_TOLERANCE
            for weight in adjusted.values()
        ):
            adjusted = {
                symbol: min(weight, limits.max_single_weight) for symbol, weight in adjusted.items()
            }
            reasons.append(f"实际单股权重超过 {limits.max_single_weight:.0%}，自动减仓")
        total_cap = min(limits.max_total_weight, 1.0 - limits.minimum_cash_ratio)
        adjusted_total = sum(adjusted.values())
        if adjusted_total > total_cap + RISK_WEIGHT_TOLERANCE:
            scale = total_cap / adjusted_total if adjusted_total > 0 else 0.0
            adjusted = {symbol: weight * scale for symbol, weight in adjusted.items()}
            reasons.append(f"实际总仓位超过 {total_cap:.0%}，自动减仓")

    if drawdown_breached:
        if limits.drawdown_action == "liquidate":
            adjusted = {}
            reasons.append(f"账户回撤达到 {limits.max_drawdown:.0%}，执行清仓")
            action = PortfolioRiskAction.LIQUIDATE
        elif limits.drawdown_action == "reduce":
            target_total = min(
                current_total,
                limits.drawdown_target_weight,
                limits.max_total_weight,
                1.0 - limits.minimum_cash_ratio,
            )
            adjusted_total = sum(adjusted.values())
            if adjusted_total > target_total + RISK_WEIGHT_TOLERANCE:
                scale = target_total / adjusted_total if adjusted_total > 0 else 0.0
                adjusted = {symbol: weight * scale for symbol, weight in adjusted.items()}
            reasons.append(
                f"账户回撤达到 {limits.max_drawdown:.0%}，仓位降至不高于 {target_total:.0%}"
            )
            action = PortfolioRiskAction.REDUCE

    changed = set(adjusted) != set(clean) or any(
        abs(adjusted.get(symbol, 0.0) - weight) > 1e-9 for symbol, weight in clean.items()
    )
    if not changed:
        return DailyPortfolioRisk(
            RiskDecision.PASS,
            PortfolioRiskAction.NONE,
            (),
            (),
            current_total,
            current_max,
            current_drawdown,
        )
    if action == PortfolioRiskAction.NONE:
        action = PortfolioRiskAction.REBALANCE
    targets = tuple(
        TargetPosition(strategy_id, trade_date, symbol, weight)
        for symbol, weight in sorted(adjusted.items())
        if weight > 1e-12
    )
    return DailyPortfolioRisk(
        RiskDecision.ADJUST,
        action,
        tuple(reasons),
        targets,
        current_total,
        current_max,
        current_drawdown,
    )
