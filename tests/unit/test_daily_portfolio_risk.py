from __future__ import annotations

from datetime import date

from quant_platform.risk.basic_rules import (
    PortfolioRiskAction,
    RiskDecision,
    evaluate_daily_portfolio_risk,
)
from quant_platform.risk.config import RiskLimits


def test_daily_position_risk_caps_drifted_holdings() -> None:
    result = evaluate_daily_portfolio_risk(
        {"A": 0.40, "B": 0.35, "C": 0.25},
        RiskLimits(max_total_weight=0.80, max_single_weight=0.30, max_positions=2),
        strategy_id="test",
        trade_date=date(2024, 1, 2),
        current_drawdown=-0.05,
    )

    assert result.decision == RiskDecision.ADJUST
    assert result.action == PortfolioRiskAction.REBALANCE
    assert len(result.targets) == 2
    assert max(target.target_weight for target in result.targets) <= 0.30
    assert sum(target.target_weight for target in result.targets) <= 0.80


def test_drawdown_reduce_creates_lower_exposure_targets() -> None:
    result = evaluate_daily_portfolio_risk(
        {"A": 0.50, "B": 0.45},
        RiskLimits(
            max_drawdown=0.20,
            drawdown_action="reduce",
            drawdown_target_weight=0.50,
        ),
        strategy_id="test",
        trade_date=date(2024, 1, 2),
        current_drawdown=-0.21,
    )

    assert result.decision == RiskDecision.ADJUST
    assert result.action == PortfolioRiskAction.REDUCE
    assert abs(sum(target.target_weight for target in result.targets) - 0.50) < 1e-9


def test_drawdown_liquidate_returns_empty_targets() -> None:
    result = evaluate_daily_portfolio_risk(
        {"A": 0.60},
        RiskLimits(max_drawdown=0.20, drawdown_action="liquidate"),
        strategy_id="test",
        trade_date=date(2024, 1, 2),
        current_drawdown=-0.25,
    )

    assert result.action == PortfolioRiskAction.LIQUIDATE
    assert result.targets == ()
