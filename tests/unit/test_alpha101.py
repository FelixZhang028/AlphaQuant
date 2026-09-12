"""Formula examples and causal prefix invariance for the shipped subset."""

import numpy as np
import pandas as pd
import pytest

from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.combine import combine_factors


@pytest.fixture
def bars():
    rows = []
    for day in range(15):
        for index, symbol in enumerate(["A", "B", "C"]):
            opening = 10 + day + index
            rows.append(
                {
                    "trade_date": pd.Timestamp("2025-01-01") + pd.Timedelta(days=day),
                    "symbol": symbol,
                    "raw_open": opening,
                    "raw_close": opening + index + 1,
                    "raw_high": opening + 5,
                    "raw_low": opening - 1,
                    "volume": (day + 1) * (index + 1) * 100,
                }
            )
    return pd.DataFrame(rows)


def test_known_formula_values_and_combination(bars):
    values = {f.name: f.compute(bars) for f in alpha101_factors()}
    last = {
        name: frame.groupby("symbol").tail(1).set_index("symbol")["value"]
        for name, frame in values.items()
    }
    np.testing.assert_allclose(last["alpha101_006"], [-1, -1, -1])
    np.testing.assert_allclose(last["alpha101_012"], [-1, -1, -1])
    np.testing.assert_allclose(last["alpha101_033"], [1, 2 / 3, 1 / 3])
    np.testing.assert_allclose(last["alpha101_101"], np.array([1, 2, 3]) / 6.001)
    original = {
        name: values[name]
        for name in ("alpha101_006", "alpha101_012", "alpha101_033", "alpha101_101")
    }
    combo = combine_factors(original, {name: 1.0 for name in original})
    assert not combo.empty
    assert np.isfinite(combo.value).all()


@pytest.mark.parametrize("factor", alpha101_factors(), ids=lambda f: f.name)
def test_future_rows_do_not_change_past(factor, bars):
    cutoff = pd.Timestamp("2025-01-12")
    prefix = factor.compute(bars[bars.trade_date <= cutoff])
    complete = factor.compute(bars)
    pd.testing.assert_frame_equal(prefix, complete[complete.date <= cutoff].reset_index(drop=True))


def test_undefined_correlation_is_missing(bars):
    bars["volume"] = 100
    factor = next(f for f in alpha101_factors() if f.name == "alpha101_006")
    assert factor.compute(bars).empty
