import math

import pandas as pd

from quant_platform.backtest.analytics import analyze_backtest, build_closed_trades
from quant_platform.backtest.metrics import calculate_metrics, calculate_monthly_returns


def test_return_metrics_include_drawdown_path_and_risk_ratios() -> None:
    nav = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(
                ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"]
            ),
            "equity": [100.0, 110.0, 99.0, 120.0],
        }
    )

    metrics = calculate_metrics(nav, initial_cash=100.0)
    monthly = calculate_monthly_returns(nav)

    assert math.isclose(metrics["cumulative_return"], 0.2)
    assert math.isclose(metrics["max_drawdown"], -0.1)
    assert metrics["max_drawdown_start_date"] == "2024-01-03"
    assert metrics["max_drawdown_trough_date"] == "2024-01-04"
    assert metrics["max_drawdown_recovery_date"] == "2024-01-05"
    assert metrics["max_drawdown_duration_trading_days"] == 2
    assert math.isclose(metrics["positive_day_ratio"], 2 / 3)
    assert metrics["sortino"] is not None
    assert metrics["calmar"] is not None
    assert math.isclose(float(monthly.iloc[0]["return"]), 0.2)


def test_fifo_trade_reconstruction_allocates_fees_and_slippage() -> None:
    fills = pd.DataFrame(
        [
            {
                "order_id": "buy-1",
                "symbol": "000001.SZ",
                "side": "BUY",
                "quantity": 100,
                "price": 10.1,
                "reference_price": 10.0,
                "commission": 5.0,
                "stamp_tax": 0.0,
                "slippage_cost": 10.0,
                "trade_date": "2024-01-02",
            },
            {
                "order_id": "sell-1",
                "symbol": "000001.SZ",
                "side": "SELL",
                "quantity": 100,
                "price": 10.8,
                "reference_price": 11.0,
                "commission": 5.0,
                "stamp_tax": 1.08,
                "slippage_cost": 20.0,
                "trade_date": "2024-01-11",
            },
        ]
    )

    trades = build_closed_trades(fills)

    assert len(trades) == 1
    trade = trades.iloc[0]
    assert math.isclose(float(trade["gross_pnl"]), 100.0)
    assert math.isclose(float(trade["direct_cost"]), 11.08)
    assert math.isclose(float(trade["slippage_cost"]), 30.0)
    assert math.isclose(float(trade["net_pnl"]), 58.92)
    assert trade["holding_days"] == 9


def test_complete_analytics_include_execution_cost_and_position_metrics() -> None:
    nav = pd.DataFrame(
        {
            "trade_date": pd.to_datetime(["2024-01-02", "2024-01-11"]),
            "cash": [0.0, 1_058.92],
            "market_value": [1_010.0, 0.0],
            "equity": [1_010.0, 1_058.92],
        }
    )
    orders = pd.DataFrame(
        {
            "order_id": ["buy-1", "sell-1", "rejected-1"],
            "status": ["FILLED", "FILLED", "REJECTED"],
        }
    )
    fills = pd.DataFrame(
        [
            {
                "order_id": "buy-1",
                "symbol": "000001.SZ",
                "side": "BUY",
                "quantity": 100,
                "price": 10.1,
                "reference_price": 10.0,
                "commission": 5.0,
                "stamp_tax": 0.0,
                "slippage_cost": 10.0,
                "trade_date": "2024-01-02",
            },
            {
                "order_id": "sell-1",
                "symbol": "000001.SZ",
                "side": "SELL",
                "quantity": 100,
                "price": 10.8,
                "reference_price": 11.0,
                "commission": 5.0,
                "stamp_tax": 1.08,
                "slippage_cost": 20.0,
                "trade_date": "2024-01-11",
            },
        ]
    )
    positions = pd.DataFrame(
        {
            "trade_date": ["2024-01-02"],
            "symbol": ["000001.SZ"],
            "market_value": [1_010.0],
        }
    )

    result = analyze_backtest(
        nav, orders, fills, positions, initial_cash=1_000.0
    ).summary

    assert math.isclose(result["total_transaction_cost"], 41.08)
    assert math.isclose(result["trade_win_rate"], 1.0)
    assert math.isclose(result["order_fill_rate"], 2 / 3)
    assert result["rejected_orders"] == 1
    assert result["max_position_count"] == 1
    assert math.isclose(result["time_in_market_ratio"], 0.5)
