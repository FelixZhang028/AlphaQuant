from __future__ import annotations

from datetime import date

from quant_platform.portfolio.models import TargetPosition
from quant_platform.risk.basic_rules import RiskDecision, evaluate_target_risk
from quant_platform.risk.config import RiskLimits


def _target(symbol: str, weight: float) -> TargetPosition:
    return TargetPosition(
        strategy_id="test",
        signal_date=date(2024, 1, 2),
        symbol=symbol,
        target_weight=weight,
    )


def test_configured_risk_returns_all_rejection_reasons() -> None:
    limits = RiskLimits(
        max_total_weight=0.8,
        max_single_weight=0.4,
        max_positions=2,
        minimum_cash_ratio=0.2,
        max_drawdown=0.15,
    )

    result = evaluate_target_risk(
        [
            _target("000001.SZ", 0.5),
            _target("000002.SZ", 0.3),
            _target("600000.SH", 0.2),
        ],
        limits,
        current_drawdown=-0.16,
    )

    assert result.decision == RiskDecision.REJECT
    assert len(result.reasons) == 4
    assert result.target_count == 3
    assert result.total_weight == 1.0


def test_disabled_risk_allows_targets() -> None:
    result = evaluate_target_risk(
        [_target("000001.SZ", 1.5)],
        RiskLimits(enabled=False),
        current_drawdown=-0.9,
    )

    assert result.decision == RiskDecision.PASS
    assert result.reasons == ()
