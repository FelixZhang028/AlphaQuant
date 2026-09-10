"""成本锚定复权因子的账户级测试：分红、送转、跨除权加仓。"""

from datetime import date

import pytest

from quant_platform.accounts.account import Account
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

    account.apply_fill(
        _fill(_order(OrderSide.SELL, 1_000, date(2024, 1, 10)), 1_000, 9.0, 10.0 / 9.0)
    )

    # 锚定结算：1000×9×(10/9)/1 = 10000 = 买入成本，盈亏为 0、现金回到起点。
    assert account.realized_pnl == pytest.approx(0.0)
    assert account.cash == pytest.approx(100_000.0)
    assert account.positions == {}


def test_cross_ex_date_add_blends_cost_anchor() -> None:
    account = Account("test", 100_000)
    # 除权前 10 元买入 1000 股（因子 1）。
    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 2)), 1_000, 10.0, 1.0))
    # 10送10 后价格腰斩、因子翻倍，5 元再加仓 1000 股。
    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 10)), 1_000, 5.0, 2.0))

    position = account.positions["000001.SZ"]
    # 调和平均锚定：2000 / (1000/1 + 1000/2) = 4/3。
    assert position.cost_adj_factor == pytest.approx(4.0 / 3.0)
    assert position.average_cost == pytest.approx(7.5)

    # 锚定估值价 = 5×2/(4/3) = 7.5，总市值 15000，
    # 与逐笔锚定的分量和一致（1000×5×2/1 + 1000×5×2/2 = 15000）。
    snapshot = account.mark_to_market(
        date(2024, 1, 10), {"000001.SZ": 5.0 * 2.0 / (4.0 / 3.0)}
    )
    assert snapshot.market_value == pytest.approx(15_000.0)
    assert snapshot.equity == pytest.approx(100_000.0)

    account.start_day()
    account.apply_fill(
        _fill(_order(OrderSide.SELL, 2_000, date(2024, 1, 12)), 2_000, 5.0, 2.0)
    )

    # 全部按锚定价结算：2000×5×2/(4/3) = 15000 = 总成本，无幻影盈亏。
    assert account.realized_pnl == pytest.approx(0.0)
    assert account.cash == pytest.approx(100_000.0)


def test_zero_factor_fill_falls_back_to_raw_ratio() -> None:
    account = Account("test", 100_000)

    account.apply_fill(_fill(_order(OrderSide.BUY, 1_000, date(2024, 1, 2)), 1_000, 10.0, 0.0))

    # 异常因子回退比率 1（未复权口径）。
    assert account.positions["000001.SZ"].cost_adj_factor == pytest.approx(1.0)
