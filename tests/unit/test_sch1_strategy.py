import numpy as np
import pandas as pd
import pytest

from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.discovery import StrategyCatalog
from quant_platform.strategies.sch1 import SCH1Parameters, SCH1Strategy


def _history(symbol_count: int = 20) -> pd.DataFrame:
    dates = pd.bdate_range("2023-01-02", periods=340)
    rows: list[dict[str, object]] = []
    for number in range(symbol_count):
        price = 10.0 + number
        growth = 0.0008 + number * 0.00005
        amplitude = 0.0005 + number * 0.00004
        for index, timestamp in enumerate(dates):
            cycle = amplitude * np.sin(index / 3.0 + number)
            price *= 1.0 + growth + cycle
            rows.append(
                {
                    "symbol": f"S{number:02d}.SZ",
                    "trade_date": timestamp,
                    "adjusted_close": price,
                }
            )
    return pd.DataFrame(rows)


def test_sch1_is_discovered() -> None:
    metadata = StrategyCatalog().get_metadata("sch1")

    assert metadata.display_name == "SCH1号"
    assert metadata.defaults()["offense_top_n"] == 15
    assert metadata.defaults()["defense_top_n"] == 10


def test_sch1_builds_explicit_weight_offense_portfolio() -> None:
    history = _history()
    trade_date = history["trade_date"].max().date()
    symbols = sorted(history["symbol"].unique())
    strategy = SCH1Strategy("sch1-test", SCH1Parameters())
    context = StrategyContext.create(trade_date, history, symbols)

    signals = strategy.generate_signals(context)
    targets = EqualWeightPortfolio(top_n=5).construct(signals)

    assert len(signals) == 15
    assert {signal.signal_type for signal in signals} == {"SCH1_OFFENSE"}
    assert len(targets) == 15
    assert sum(target.target_weight for target in targets) == pytest.approx(1.0)
    assert all(target.target_weight == pytest.approx(1.0 / 15.0) for target in targets)


def test_sch1_drawdown_brake_switches_to_ten_low_volatility_stocks() -> None:
    history = _history()
    trade_date = history["trade_date"].max().date()
    symbols = sorted(history["symbol"].unique())
    strategy = SCH1Strategy("sch1-test", SCH1Parameters())
    context = StrategyContext.create(
        trade_date,
        history,
        symbols,
        portfolio_drawdown=-0.16,
    )

    signals = strategy.generate_signals(context)

    assert len(signals) == 10
    assert {signal.signal_type for signal in signals} == {"SCH1_DEFENSE"}
    assert all(signal.target_weight == pytest.approx(0.1) for signal in signals)


def test_sch1_rejects_invalid_momentum_windows() -> None:
    with pytest.raises(ValueError, match="skip < lookback"):
        SCH1Strategy(
            "sch1-test",
            SCH1Parameters(momentum_lookback=20, momentum_skip=21),
        )
