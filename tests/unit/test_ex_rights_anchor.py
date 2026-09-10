"""实际现金和股数的账户级测试：分红、送转、跨除权加仓。"""

from dataclasses import asdict
from datetime import date

import pandas as pd
import pytest

from quant_platform.accounts.account import Account
from quant_platform.accounts.models import CorporateAction
from quant_platform.backtest.analytics import build_closed_trades
from quant_platform.core.exceptions import AccountError
from quant_platform.execution.models import Fill, Order, OrderSide


def _order(side: OrderSide, quantity: int, day: date) -> Order:
    return Order.create("test", "000001.SZ", side, quantity, day, day)


def _fill(order: Order, quantity: int, price: float, adj_factor: float) -> Fill:
    return Fill.create(order, quantity, price, 0.0, 0.0, adj_factor=adj_factor)


def test_buy_records_cost_anchor_factor() -> None:
    account = Account("test", 100_000)

    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 2)), 1_000, 10.0, 2.5))

    assert account.positions["000001.SZ"].cost_adj_factor == pytest.approx(2.5)


def test_cash_dividend_sell_settles_without_phantom_loss() -> None:
    account = Account("test", 100_000)
    # 除权前 10 元买入；每股现金分红 1 元后，除权价 9 元、因子 10/9。
    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 2)), 1_000, 10.0, 1.0))
    account.start_day()
    account.apply_corporate_action(
        CorporateAction("000001.SZ", date(2024, 1, 10), cash_per_share=1)
    )

    account.apply_fill(
        _fill(_order(OrderSide.SELL, 1_000, date(2024, 1, 10)), 1_000, 9.0, 10.0 / 9.0)
    )

    # 真实分红 1000 元 + 实际卖出 9000 元，合计收回 10000 元。
    assert account.realized_pnl == pytest.approx(0.0)
    assert account.cash == pytest.approx(100_000.0)
    assert account.positions == {}


def test_cross_ex_date_add_uses_actual_shares_and_cost() -> None:
    account = Account("test", 100_000)
    # 除权前 10 元买入 1000 股（因子 1）。
    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 2)), 1_000, 10.0, 1.0))
    account.start_day()
    account.apply_corporate_action(
        CorporateAction("000001.SZ", date(2024, 1, 10), share_multiplier=2)
    )
    # 10送10 后价格腰斩、因子翻倍，5 元再加仓 1000 股。
    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 10)), 1_000, 5.0, 2.0))

    position = account.positions["000001.SZ"]
    assert position.quantity == 3000
    assert position.available_quantity == 2000
    assert position.average_cost == pytest.approx(5)

    snapshot = account.mark_to_market(date(2024, 1, 10), {"000001.SZ": 5.0})
    assert snapshot.market_value == pytest.approx(15_000.0)
    assert snapshot.equity == pytest.approx(100_000.0)

    account.start_day()
    account.apply_fill(_fill(_order(OrderSide.SELL, 3_000, date(2024, 1, 12)), 3_000, 5.0, 2.0))

    # 实际卖出 3000 股 × 5 元，费用和成交额使用同一口径。
    assert account.realized_pnl == pytest.approx(0.0)
    assert account.cash == pytest.approx(100_000.0)


def test_zero_factor_fill_falls_back_to_raw_ratio() -> None:
    account = Account("test", 100_000)

    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 2)), 1_000, 10.0, 0.0))

    # 异常因子回退比率 1（未复权口径）。
    assert account.positions["000001.SZ"].cost_adj_factor == pytest.approx(1.0)


def test_dividend_does_not_grow_with_later_stock_price() -> None:
    account = Account("test", 100_000)
    buy = _fill(_order(OrderSide.BUY, 1000, date(2024, 1, 2)), 1000, 10, 1)
    account.apply_fill(buy)
    account.start_day(date(2024, 1, 10))
    action = CorporateAction("000001.SZ", date(2024, 1, 10), cash_per_share=1)
    account.apply_corporate_action(action)
    sell = _fill(_order(OrderSide.SELL, 1000, date(2024, 2, 2)), 1000, 18, 10 / 9)
    account.apply_fill(sell)
    assert account.cash == pytest.approx(109_000)
    assert account.realized_pnl == pytest.approx(9000)
    trades = build_closed_trades(
        pd.DataFrame([asdict(buy), asdict(sell)]), corporate_actions=[action]
    )
    assert trades.net_pnl.sum() == pytest.approx(9000)
    assert trades.sell_price.tolist() == [18]
    assert trades.dividend_income.sum() == 1000


def test_split_partial_sale_charges_fees_on_actual_notional() -> None:
    account = Account("test", 100_000)
    buy = _fill(_order(OrderSide.BUY, 1000, date(2024, 1, 2)), 1000, 10, 1)
    account.apply_fill(buy)
    account.start_day()
    action = CorporateAction("000001.SZ", date(2024, 1, 10), share_multiplier=2)
    account.apply_corporate_action(action)
    order = _order(OrderSide.SELL, 1000, date(2024, 1, 10))
    sell = Fill.create(order, 1000, 5, 5, 2.5, adj_factor=2)
    account.apply_fill(sell)
    assert account.cash == pytest.approx(94992.5)
    assert account.positions[order.symbol].quantity == 1000
    assert account.positions[order.symbol].average_cost == 5
    trades = build_closed_trades(
        pd.DataFrame([asdict(buy), asdict(sell)]), corporate_actions=[action]
    )
    assert trades.net_pnl.sum() == pytest.approx(-7.5)


def test_delayed_entitlements_are_valued_but_not_spendable_or_sellable() -> None:
    account = Account("test", 100_000)
    account.apply_fill(_fill(_order(OrderSide.BUY, 1000, date(2024, 1, 2)), 1000, 10, 1))
    account.start_day(date(2024, 1, 10))
    action = CorporateAction(
        "000001.SZ",
        date(2024, 1, 10),
        cash_per_share=1,
        share_multiplier=2,
        pay_date=date(2024, 1, 15),
        share_listing_date=date(2024, 1, 16),
    )
    account.apply_corporate_action(action)
    assert account.cash == 90000
    assert account.dividend_receivable == 1000
    assert account.mark_to_market(date(2024, 1, 10), {"000001.SZ": 4.5}).equity == 100000
    account.start_day(date(2024, 1, 11))
    assert account.positions["000001.SZ"].available_quantity == 1000
    with pytest.raises(AccountError, match="Insufficient sellable"):
        account.apply_fill(_fill(_order(OrderSide.SELL, 2000, date(2024, 1, 11)), 2000, 4.5, 2))
    account.start_day(date(2024, 1, 15))
    assert account.cash == 91000
    assert account.dividend_receivable == 0
    account.start_day(date(2024, 1, 16))
    assert account.positions["000001.SZ"].available_quantity == 2000
    with pytest.raises(AccountError, match="already processed"):
        account.apply_corporate_action(action)


def test_ex_date_new_purchase_has_no_dividend_entitlement() -> None:
    account = Account("test", 100000)
    account.apply_corporate_action(
        CorporateAction("000001.SZ", date(2024, 1, 10), cash_per_share=1)
    )
    account.apply_fill(_fill(_order(OrderSide.BUY, 1000, date(2024, 1, 10)), 1000, 9, 10 / 9))
    assert account.cash == 91000
    assert account.realized_pnl == 0
