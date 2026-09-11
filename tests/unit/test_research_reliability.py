from datetime import date

import numpy as np
import pandas as pd
import pytest

from quant_platform.accounts.account import Account
from quant_platform.backtest.relative_metrics import relative_metrics
from quant_platform.execution.costs import stamp_rate, transfer_rate
from quant_platform.execution.models import Order, OrderSide
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel
from quant_platform.factors.statistics import ic_statistics, neutralize_exposures
from quant_platform.portfolio.models import TargetPosition
from quant_platform.portfolio.risk_weighted import RiskWeightedPortfolio, constrain_turnover
from quant_platform.risk.basic_rules import (
    PortfolioRiskAction,
    RiskDecision,
    evaluate_daily_portfolio_risk,
    evaluate_target_risk,
)
from quant_platform.risk.config import RiskLimits
from quant_platform.signals.models import Signal
from quant_platform.universe.a_share import AShareUniverseConfig
from quant_platform.universe.historical import HistoricalUniverse


def order(quantity=1000, side=OrderSide.BUY, day=date(2024, 1, 3)):
    return Order.create("test", "000001.SZ", side, quantity, date(2024, 1, 2), day)


def market(volume=10_000):
    return pd.DataFrame(
        [
            dict(
                symbol="000001.SZ",
                volume=volume,
                liquidity_volume=volume,
                raw_open=10.0,
                up_limit=11.0,
                down_limit=9.0,
                is_suspended=False,
                quality_status="OK",
            )
        ]
    )


def test_capacity_shared_across_orders_and_calls():
    model = NextOpenExecutionModel(ExecutionConfig(max_participation=0.05))
    account = Account("test", 1_000_000)
    updated, fills = model.execute([order(300), order(400)], market(), account)
    assert sum(fill.quantity for fill in fills) == 500
    assert updated[-1].remaining_quantity == 200
    rejected, fills = model.execute([order()], market(), account)
    assert not fills
    assert rejected[0].reject_reason == "LIQUIDITY_LIMIT"


def test_missing_and_zero_volume_never_fill():
    for data in (market(0), market().drop(columns=["volume"])):
        _, fills = NextOpenExecutionModel(ExecutionConfig()).execute(
            [order()], data, Account("test", 100_000)
        )
        assert not fills


def test_prior_volume_limits_opening_capacity():
    data = market(1_000_000)
    data["liquidity_volume"] = 1000
    _, fills = NextOpenExecutionModel(ExecutionConfig(max_participation=0.1)).execute(
        [order()], data, Account("test", 100_000)
    )
    assert fills[0].quantity == 100


def test_sell_is_capacity_limited_and_fees_balance():
    account = Account("test", 100_000)
    model = NextOpenExecutionModel(
        ExecutionConfig(max_participation=0.1, impact_coefficient=0, slippage_rate=0)
    )
    _, buys = model.execute([order()], market(), account)
    buy = buys[0]
    assert account.cash == pytest.approx(100_000 - 10_000 - 5 - 0.1)
    next_day = date(2024, 1, 4)
    account.start_day(next_day)
    _, sells = model.execute([order(side=OrderSide.SELL, day=next_day)], market(2000), account)
    sell = sells[0]
    assert sell.quantity == 200
    assert sell.stamp_tax == 1
    assert sell.transfer_fee == pytest.approx(0.02)
    assert account.cash == pytest.approx(
        100_000 - buy.quantity * buy.price - buy.commission - buy.transfer_fee + 2000 - 5 - 1 - 0.02
    )


def test_tax_boundaries():
    assert stamp_rate(date(2023, 8, 25)) == 0.001
    assert stamp_rate(date(2023, 8, 28)) == 0.0005
    assert transfer_rate(date(2022, 4, 28), "000001.SZ") == 0.00002
    assert transfer_rate(date(2022, 4, 29), "000001.SZ") == 0.00001
    with pytest.raises(ValueError):
        transfer_rate(date(2010, 1, 1), "000001.SZ")


def test_daily_order_limit_spans_calls():
    model = NextOpenExecutionModel(ExecutionConfig(max_orders_per_day=1))
    account = Account("test", 100_000)
    model.execute([order(100)], market(1_000_000), account)
    rejected, fills = model.execute([order(100)], market(1_000_000), account)
    assert not fills and rejected[0].reject_reason == "DAILY_ORDER_LIMIT"


def test_benchmark_regression_recovers_known_exposure():
    x = np.array([0.01, -0.02, 0.03, 0.005, -0.01])
    y = 0.001 + 1.5 * x
    nav = pd.DataFrame(
        {
            "trade_date": pd.date_range("2024-01-01", periods=6),
            "equity": 100 * np.r_[1, np.cumprod(1 + y)],
            "benchmark_equity": 100 * np.r_[1, np.cumprod(1 + x)],
        }
    )
    result = relative_metrics(nav)
    assert result["beta"] == pytest.approx(1.5)
    assert result["regression_alpha"] == pytest.approx(0.252)
    assert result["tracking_error"] == pytest.approx((y - x).std(ddof=1) * np.sqrt(252))


def test_historical_membership_includes_delisted_but_not_future_members():
    membership = pd.DataFrame(
        [
            ["OLD", "2020-01-01", "2024-01-05", "2020-01-01"],
            ["NEW", "2024-01-01", None, "2024-01-04"],
        ],
        columns=["symbol", "effective_from", "effective_to", "known_at"],
    )
    master = pd.DataFrame(
        {
            "symbol": ["OLD", "NEW"],
            "list_date": ["2010-01-01"] * 2,
            "delist_date": ["2024-01-04", None],
        }
    )
    universe = HistoricalUniverse(
        AShareUniverseConfig(("NEW",), minimum_history_days=1, minimum_average_amount=0),
        membership,
        master,
    )
    bars = pd.DataFrame(
        [
            dict(
                symbol=s,
                trade_date=d,
                amount=100,
                quality_status="OK",
                is_listed=True,
                is_st=False,
                is_suspended=False,
            )
            for d in pd.date_range("2024-01-01", periods=5)
            for s in ["OLD", "NEW"]
        ]
    )
    universe.prepare(bars)
    assert universe.select(date(2024, 1, 3), bars) == ["OLD"]
    assert universe.select(date(2024, 1, 5), bars) == ["NEW"]


def test_neutralization_cannot_use_future_exposures():
    values = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-01"] * 6),
            "symbol": list("ABCDEF"),
            "value": [1.0, 2.0, 3.0, 5.0, 6.0, 7.0],
        }
    )
    exposure = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02"] * 6),
            "symbol": list("ABCDEF"),
            "industry": ["X"] * 3 + ["Y"] * 3,
        }
    )
    with pytest.raises(ValueError, match="当时可得"):
        neutralize_exposures(values, exposure, "industry")
    exposure["date"] = pd.Timestamp("2024-01-01")
    output = neutralize_exposures(values, exposure, "industry")
    np.testing.assert_allclose(output.value, [-1, 0, 1, -1, 0, 1], atol=1e-12)


def test_missing_research_inputs_fail_explicitly():
    with pytest.raises(ValueError, match="universe_membership"):
        HistoricalUniverse(AShareUniverseConfig(("A",)), pd.DataFrame(), pd.DataFrame())
    with pytest.raises(ValueError, match="security_exposures"):
        neutralize_exposures(pd.DataFrame(), pd.DataFrame(), "both")


def test_hac_and_turnover_and_risk():
    result = ic_statistics(pd.Series(np.random.default_rng(9).normal(0.05, 0.1, 200)), 5)
    assert 0 <= result["hac_p"] < 0.05
    assert np.isnan(ic_statistics(pd.Series([0.1] * 5), 5)["hac_p"])
    targets = [TargetPosition("s", date(2024, 1, 1), "A", 1)]
    limited = constrain_turnover(targets, {"B": 1.0}, 0.4)
    weights = {t.symbol: t.target_weight for t in limited}
    assert weights == pytest.approx({"A": 0.2, "B": 0.8})
    liquidation = constrain_turnover([], {"B": 1.0}, 0.4, reference=targets[0])
    assert {t.symbol: t.target_weight for t in liquidation} == pytest.approx({"B": 0.6})
    check = evaluate_target_risk(
        targets, RiskLimits(max_industry_weight=0.5), industry_map={"A": "bank"}
    )
    assert check.decision == RiskDecision.REJECT
    daily = evaluate_daily_portfolio_risk(
        {"A": 1},
        RiskLimits(max_daily_loss=0.05),
        strategy_id="s",
        trade_date=date(2024, 1, 1),
        current_drawdown=-0.06,
        daily_return=-0.06,
    )
    assert daily.action == PortfolioRiskAction.STOP_NEW


@pytest.mark.parametrize("method", ["inverse_volatility", "risk_parity", "mean_variance"])
def test_risk_allocations_are_long_only_and_causal(method):
    rng = np.random.default_rng(2)
    dates = pd.bdate_range("2024-01-01", periods=61)
    bars = pd.DataFrame(
        [
            dict(trade_date=d, symbol=s, adjusted_close=p)
            for s, sigma in [("A", 0.01), ("B", 0.03)]
            for d, p in zip(dates, 100 * np.cumprod(1 + rng.normal(0, sigma, 61)), strict=True)
        ]
    )
    signals = [Signal("s", dates[-1].date(), s, "test", 1) for s in ["A", "B"]]
    targets = RiskWeightedPortfolio(2, method).construct_with_history(signals, bars)
    assert sum(t.target_weight for t in targets) == pytest.approx(1)
    assert all(t.target_weight >= 0 for t in targets)
    future = bars.copy()
    future["trade_date"] += pd.Timedelta(days=366)
    future["adjusted_close"] *= 100
    with_future = RiskWeightedPortfolio(2, method).construct_with_history(
        signals, pd.concat([bars, future], ignore_index=True)
    )
    assert [t.target_weight for t in with_future] == pytest.approx(
        [t.target_weight for t in targets]
    )
    if method == "inverse_volatility":
        assert targets[0].target_weight > targets[1].target_weight
