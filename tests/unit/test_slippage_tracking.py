import math
from datetime import date

import pandas as pd

from quant_platform.accounts.account import Account
from quant_platform.execution.models import Order, OrderSide
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel


def test_next_open_fill_records_reference_price_and_slippage_cost() -> None:
    account = Account("slippage", 100_000.0)
    order = Order.create(
        "slippage",
        "000001.SZ",
        OrderSide.BUY,
        1_000,
        date(2024, 1, 2),
        date(2024, 1, 3),
    )
    market = pd.DataFrame(
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

    _, fills = NextOpenExecutionModel(ExecutionConfig(slippage_rate=0.01)).execute(
        [order], market, account
    )

    assert len(fills) == 1
    assert fills[0].reference_price == 10.0
    assert math.isclose(fills[0].price, 10.1)
    assert math.isclose(fills[0].slippage_cost, 100.0)
