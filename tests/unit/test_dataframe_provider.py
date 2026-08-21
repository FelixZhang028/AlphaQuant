"""DataFrameProvider 单元测试：快照截断、排序、回填与数据不足报错。"""

from datetime import date

import pandas as pd
import pytest

from quant_platform.agents_bridge.provider import DataFrameProvider


def _frame(symbol: str = "000001.SZ", periods: int = 80) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trade_date": dates,
            "raw_open": 10.0,
            "raw_high": 10.5,
            "raw_low": 9.8,
            "raw_close": [10.0 + i * 0.1 for i in range(periods)],
            "volume": 1_000_000,
            "amount": 10_000_000.0,
        }
    )


def test_snapshot_truncates_after_as_of_date() -> None:
    provider = DataFrameProvider({"000001.SZ": _frame()})
    ticker = provider.resolve("000001.SZ", "CN")
    as_of = date(2024, 2, 29)

    snapshot = provider.get_snapshot(ticker, as_of)

    assert snapshot.bars, "快照不应为空"
    assert all(bar.date <= as_of for bar in snapshot.bars)
    assert snapshot.as_of_date == as_of
    assert snapshot.last_close == snapshot.bars[-1].close


def test_snapshot_respects_lookback_and_ascending_order() -> None:
    provider = DataFrameProvider({"000001.SZ": _frame(periods=80)})
    ticker = provider.resolve("000001.SZ", "CN")

    snapshot = provider.get_snapshot(ticker, date(2024, 4, 26), lookback_days=10)

    assert len(snapshot.bars) == 10
    dates = [bar.date for bar in snapshot.bars]
    assert dates == sorted(dates)
    assert isinstance(snapshot.bars[0].volume, int)


def test_resolve_uses_names_mapping() -> None:
    provider = DataFrameProvider(
        {"000001.SZ": _frame()}, names={"000001.SZ": "平安银行"}
    )
    ticker = provider.resolve("000001.SZ", "CN")
    assert ticker.name == "平安银行"
    assert ticker.currency == "CNY"


def test_get_bars_after_excludes_start_date() -> None:
    frame = _frame(periods=10)
    provider = DataFrameProvider({"000001.SZ": frame})
    ticker = provider.resolve("000001.SZ", "CN")
    start = pd.Timestamp(frame["trade_date"].iloc[2]).date()

    bars = provider.get_bars_after(ticker, start, days=3)

    assert len(bars) == 3
    assert all(bar.date > start for bar in bars)
    assert bars[0].date == pd.Timestamp(frame["trade_date"].iloc[3]).date()


def test_snapshot_raises_value_error_when_no_data_before_as_of() -> None:
    provider = DataFrameProvider({"000001.SZ": _frame()})
    ticker = provider.resolve("000001.SZ", "CN")

    with pytest.raises(ValueError, match="没有可用行情数据"):
        provider.get_snapshot(ticker, date(2020, 1, 1))


def test_unknown_symbol_raises_value_error() -> None:
    provider = DataFrameProvider({"000001.SZ": _frame()})
    ticker = provider.resolve("600000.SH", "CN")

    with pytest.raises(ValueError, match="600000.SH"):
        provider.get_snapshot(ticker, date(2024, 4, 26))
