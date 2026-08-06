from datetime import date

import pandas as pd
import pytest

from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.discovery import StrategyCatalog
from quant_platform.strategies.wt1 import WT1Parameters, WT1Strategy


def _history() -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-01", periods=100)
    rows: list[dict[str, object]] = []
    definitions = (
        ("FAST.SZ", 0.0040, 100_000_000.0),
        ("SLOW.SZ", 0.0010, 80_000_000.0),
        ("DOWN.SZ", -0.0010, 100_000_000.0),
        ("DRY.SZ", 0.0030, 1_000_000.0),
    )
    for symbol, growth, amount in definitions:
        raw_close = 10.0
        for index, timestamp in enumerate(dates):
            raw_close *= 1.0 + growth + (0.0005 if index % 7 == 0 else 0.0)
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": timestamp,
                    "adjusted_close": raw_close,
                    "raw_close": raw_close,
                    "raw_high": raw_close * 1.01,
                    "raw_low": raw_close * 0.99,
                    "amount": amount,
                }
            )
    return pd.DataFrame(rows)


def test_wt1_is_discovered_with_all_parameters() -> None:
    catalog = StrategyCatalog()

    assert "wt1" in catalog.names()
    metadata = catalog.get_metadata("wt1")
    assert metadata.display_name == "WT1号"
    assert set(metadata.defaults()) == {
        "short_window",
        "long_window",
        "minimum_average_amount",
        "ma_fast",
        "ma_slow",
        "kdj_period",
        "minimum_score",
    }


def test_wt1_filters_trend_and_liquidity_then_ranks_candidates() -> None:
    history = _history()
    trade_date = history["trade_date"].max().date()
    strategy = WT1Strategy(
        "wt1-test",
        WT1Parameters(minimum_average_amount=20_000_000.0, minimum_score=-1.0),
    )
    context = StrategyContext.create(
        trade_date,
        history,
        ["FAST.SZ", "SLOW.SZ", "DOWN.SZ", "DRY.SZ"],
    )

    signals = strategy.generate_signals(context)

    assert [signal.symbol for signal in signals] == ["FAST.SZ", "SLOW.SZ"]
    assert signals[0].score > signals[1].score
    assert all(-1.0 <= signal.score <= 1.0 for signal in signals)
    assert all(signal.model_version == "WT1-v1" for signal in signals)


def test_wt1_default_threshold_can_keep_cash() -> None:
    history = _history()
    trade_date = history["trade_date"].max().date()
    strategy = WT1Strategy("wt1-test", WT1Parameters())
    context = StrategyContext.create(trade_date, history, ["FAST.SZ", "SLOW.SZ"])

    signals = strategy.generate_signals(context)

    assert [signal.symbol for signal in signals] == ["FAST.SZ"]


def test_wt1_rejects_inconsistent_windows() -> None:
    with pytest.raises(ValueError, match="short_window < long_window"):
        WT1Strategy("wt1-test", WT1Parameters(short_window=60, long_window=20))

    with pytest.raises(ValueError, match="ma_fast < ma_slow"):
        WT1Strategy("wt1-test", WT1Parameters(ma_fast=20, ma_slow=10))


def test_wt1_ignores_future_rows() -> None:
    history = _history()
    signal_date = date(2024, 4, 30)
    strategy = WT1Strategy("wt1-test", WT1Parameters(minimum_score=-1.0))
    universe = ["FAST.SZ", "SLOW.SZ"]

    before = strategy.generate_signals(StrategyContext.create(signal_date, history, universe))
    history.loc[history["trade_date"] > pd.Timestamp(signal_date), "adjusted_close"] *= 100
    after = strategy.generate_signals(StrategyContext.create(signal_date, history, universe))

    assert before == after
