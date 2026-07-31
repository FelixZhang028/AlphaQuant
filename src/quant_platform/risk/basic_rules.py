"""Configurable target-weight risk checks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from quant_platform.portfolio.models import TargetPosition
from quant_platform.risk.config import RiskLimits


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
