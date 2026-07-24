"""Minimal target-weight risk checks."""

from __future__ import annotations

from enum import StrEnum

from quant_platform.portfolio.models import TargetPosition


class RiskDecision(StrEnum):
    """Risk evaluation result."""

    PASS = "PASS"
    ADJUST = "ADJUST"
    REJECT = "REJECT"


def validate_target_weights(targets: list[TargetPosition]) -> RiskDecision:
    """Reject negative weights or total exposure above 100 percent."""

    if any(target.target_weight < 0 or target.target_weight > 1 for target in targets):
        return RiskDecision.REJECT
    if sum(target.target_weight for target in targets) > 1.0 + 1e-9:
        return RiskDecision.REJECT
    return RiskDecision.PASS
