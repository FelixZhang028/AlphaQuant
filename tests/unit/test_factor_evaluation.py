"""Hand-calculated regression cases for factor evaluation conventions."""

from types import SimpleNamespace

import pandas as pd
import pytest

from quant_platform.factors.evaluation import FactorEvaluator


class Repository:
    def __init__(self, bars):
        self.bars = bars

    def get_daily_bars(self, symbols=None, end_date=None):
        bars = self.bars.copy()
        if symbols:
            bars = bars[bars.symbol.isin(symbols)]
        if end_date is not None:
            bars = bars[bars.trade_date <= pd.Timestamp(end_date)]
        return bars


@pytest.mark.parametrize(("horizon", "expected"), [(1, 0.5), (5, 3.0)])
def test_forward_returns_hold_full_n_days(horizon, expected):
    bars = pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-01", periods=7),
        "symbol": "A", "raw_close": [10, 20, 30, 40, 50, 60, 80],
    })
    result = FactorEvaluator(Repository(bars))._forward_returns(None, horizon)
    assert result.iloc[0].fwd_ret == pytest.approx(expected)
    assert len(result) == 7 - horizon - 1


@pytest.mark.parametrize("bad_price", [0, -1, float("nan"), float("inf")])
def test_missing_or_invalid_entry_is_not_filled(bad_price):
    bars = pd.DataFrame({
        "trade_date": pd.bdate_range("2026-01-01", periods=4),
        "symbol": "A", "raw_close": [10, bad_price, 30, 40],
    })
    result = FactorEvaluator(Repository(bars))._forward_returns(None, 1)
    assert bars.trade_date.iloc[0] not in set(result.date)
    assert result.iloc[-1].fwd_ret == pytest.approx(40 / 30 - 1)


def test_long_short_pairs_dates_without_regrouping_missing_returns():
    values = pd.DataFrame({
        "date": [pd.Timestamp("2026-01-01")] * 4 + [pd.Timestamp("2026-01-02")] * 4,
        "symbol": list("ABCD") * 2,
        "adjusted": [1, 2, 3, 4] * 2,
        "fwd_ret": [None, None, 10, 10, 0.1, 0.1, 0.3, 0.3],
    })
    frame, _, spread = FactorEvaluator._group_returns(values, 2)
    assert frame[frame.date == pd.Timestamp("2026-01-01")]["group"].tolist() == [2]
    assert spread == pytest.approx(0.2)


@pytest.mark.parametrize("scores", [[1, 1, 1, 1], [1, 1, 1, 2], [1]])
def test_incomplete_quantiles_are_not_used(scores):
    values = pd.DataFrame({
        "date": pd.Timestamp("2026-01-01"), "adjusted": scores,
        "fwd_ret": 0.1, "symbol": [str(i) for i in range(len(scores))],
    })
    frame, _, spread = FactorEvaluator._group_returns(values, 2)
    assert frame.empty
    assert pd.isna(spread)
    assert FactorEvaluator._top_turnover(values, 2).empty


def test_turnover_uses_signal_membership_even_without_future_labels():
    dates = pd.bdate_range("2026-01-01", periods=4)
    bars = pd.DataFrame([
        {"trade_date": day, "symbol": symbol, "raw_close": 10 + d + i,
         "score": ([1, 2, 3, 4] if d == 0 else [1, 3, 2, 4])[i]}
        for d, day in enumerate(dates) for i, symbol in enumerate("ABCD")
    ])
    factor = SimpleNamespace(
        name="test", display_name="Test", direction=1,
        compute=lambda frame: frame.rename(columns={"trade_date": "date", "score": "value"})[
            ["date", "symbol", "value"]
        ],
    )
    reports = []
    for horizon in (1, 5):
        report = FactorEvaluator(Repository(bars)).evaluate(
            factor, dates[0].date(), dates[-1].date(), horizon=horizon, n_groups=2
        )
        reports.append(report)
        assert report.turnover.turnover.tolist() == [0.5, 0.0, 0.0]
    pd.testing.assert_frame_equal(reports[0].turnover, reports[1].turnover)
    assert reports[1].daily_ic.empty


def test_turnover_does_not_bridge_missing_signal_dates():
    dates = pd.bdate_range("2026-01-01", periods=3)
    values = pd.DataFrame({
        "date": [dates[0]] * 4 + [dates[2]] * 4,
        "symbol": list("ABCD") * 2, "adjusted": [1, 2, 3, 4] * 2,
    })
    assert FactorEvaluator._top_turnover(values, 2, dates=dates).empty
