from datetime import date

import pandas as pd

from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.momentum import (
    AShareMomentumStrategy,
    MomentumParameters,
)


def _history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=70)
    rows: list[dict[str, object]] = []
    for symbol, growth in (("AAA.SZ", 0.003), ("BBB.SZ", 0.001), ("CCC.SZ", -0.001)):
        price = 10.0
        for timestamp in dates:
            price *= 1 + growth
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": timestamp,
                    "adjusted_close": price,
                    "amount": 100_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def test_momentum_filters_negative_trend_and_equal_weights() -> None:
    history = _history()
    trade_date = history["trade_date"].max().date()
    strategy = AShareMomentumStrategy("momentum", MomentumParameters(20, 60, 1.0))
    context = StrategyContext.create(
        trade_date, history, ["AAA.SZ", "BBB.SZ", "CCC.SZ"]
    )

    signals = strategy.generate_signals(context)
    targets = EqualWeightPortfolio(top_n=2).construct(signals)

    assert [signal.symbol for signal in signals] == ["AAA.SZ", "BBB.SZ"]
    assert sum(target.target_weight for target in targets) == 1.0
    assert all(target.target_weight == 0.5 for target in targets)


def test_strategy_context_does_not_expose_future_rows() -> None:
    history = _history()
    signal_date = date(2024, 3, 29)
    strategy = AShareMomentumStrategy("momentum", MomentumParameters(5, 10, 1.0))
    before = strategy.generate_signals(
        StrategyContext.create(signal_date, history, ["AAA.SZ"])
    )
    history.loc[
        history["trade_date"] > pd.Timestamp(signal_date), "adjusted_close"
    ] *= 100
    after = strategy.generate_signals(
        StrategyContext.create(signal_date, history, ["AAA.SZ"])
    )

    assert before == after
