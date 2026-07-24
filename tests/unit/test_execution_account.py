from datetime import date

import pandas as pd
import pytest

from quant_platform.accounts.account import Account
from quant_platform.core.exceptions import AccountError
from quant_platform.execution.models import Order, OrderSide, OrderStatus
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel


def _market_row() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "raw_open": 10.0,
                "up_limit": 11.0,
                "down_limit": 9.0,
                "is_suspended": False,
                "quality_status": "OK",
            }
        ]
    )


def test_next_open_fill_updates_cash_and_t_plus_one_position() -> None:
    account = Account("test", 100_000)
    order = Order.create(
        "test", "000001.SZ", OrderSide.BUY, 1_000, date(2024, 1, 2), date(2024, 1, 3)
    )
    model = NextOpenExecutionModel(ExecutionConfig(slippage_rate=0.0))

    orders, fills = model.execute([order], _market_row(), account)

    assert orders[0].status == OrderStatus.FILLED
    assert account.positions["000001.SZ"].quantity == 1_000
    assert account.positions["000001.SZ"].available_quantity == 0
    assert account.cash < 90_000
    with pytest.raises(AccountError):
        account.apply_fill(fills[0])


def test_limit_up_rejects_buy() -> None:
    account = Account("test", 100_000)
    order = Order.create(
        "test", "000001.SZ", OrderSide.BUY, 1_000, date(2024, 1, 2), date(2024, 1, 3)
    )
    market = _market_row()
    market.loc[0, "raw_open"] = 11.0

    orders, fills = NextOpenExecutionModel(ExecutionConfig()).execute(
        [order], market, account
    )

    assert orders[0].status == OrderStatus.REJECTED
    assert fills == []
