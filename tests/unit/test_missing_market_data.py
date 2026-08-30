"""回测数据缺口回归测试：停牌/缺失行情不得再抛 NoneType 或按 0 估值。"""

from datetime import date

import pandas as pd

from quant_platform.accounts.account import Account
from quant_platform.backtest.engine import BacktestEngine
from quant_platform.execution.models import Order, OrderSide, OrderStatus
from quant_platform.execution.next_open import ExecutionConfig, NextOpenExecutionModel


def _order() -> Order:
    return Order.create(
        "test", "000001.SZ", OrderSide.BUY, 1_000, date(2024, 1, 2), date(2024, 1, 3)
    )


def test_missing_raw_open_rejects_instead_of_none_type_error() -> None:
    """执行日行情存在但开盘价为 None：拒单而不是 TypeError: float(None)。"""
    account = Account("test", 100_000)
    market = pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "raw_open": None,
                "up_limit": 11.0,
                "down_limit": 9.0,
                "is_suspended": False,
                "quality_status": "OK",
            }
        ]
    )

    orders, fills = NextOpenExecutionModel(ExecutionConfig()).execute(
        [_order()], market, account
    )

    assert orders[0].status == OrderStatus.REJECTED
    assert orders[0].reject_reason == "INVALID_EXECUTION_PRICE"
    assert fills == []


def test_non_positive_raw_open_is_rejected() -> None:
    account = Account("test", 100_000)
    market = pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "raw_open": 0.0,
                "up_limit": 11.0,
                "down_limit": 9.0,
                "is_suspended": False,
                "quality_status": "OK",
            }
        ]
    )

    orders, fills = NextOpenExecutionModel(ExecutionConfig()).execute(
        [_order()], market, account
    )

    assert orders[0].status == OrderStatus.REJECTED
    assert orders[0].reject_reason == "INVALID_EXECUTION_PRICE"
    assert fills == []


def test_seed_closing_prices_uses_latest_close_before_start() -> None:
    """回测区间内没有数据的股票，用起点前最后收盘价估值而不是 0/None。"""
    bars = pd.DataFrame(
        [
            {"symbol": "600000.SH", "trade_date": pd.Timestamp("2023-12-20"), "raw_close": 9.5},
            {"symbol": "600000.SH", "trade_date": pd.Timestamp("2023-12-29"), "raw_close": 10.5},
            {"symbol": "000001.SZ", "trade_date": pd.Timestamp("2024-01-02"), "raw_close": 12.0},
        ]
    ).sort_values("trade_date")

    seeded = BacktestEngine._seed_closing_prices(bars, date(2024, 1, 1))

    assert seeded == {"600000.SH": 10.5}
