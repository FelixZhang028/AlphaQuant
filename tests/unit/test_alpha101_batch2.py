"""Batch-two independent array oracle, causality, and data contracts."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import rankdata
from streamlit.testing.v1 import AppTest

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.alpha101_batch2 import batch2_factors

NUMBERS = [5, 8, 11, 19, 21, 24, 25, 27, 28, 30, 32, 37, 41, 42, 45, 46, 47, 49, 50, 51]


@pytest.fixture(scope="module")
def market():
    rng = np.random.default_rng(563)
    c = 50 + rng.normal(size=(290, 7)).cumsum(axis=0)
    o = c + rng.normal(size=c.shape)
    h = np.maximum(o, c) + rng.uniform(0.1, 2, c.shape)
    low = np.minimum(o, c) - rng.uniform(0.1, 2, c.shape)
    v = rng.uniform(100, 5000, c.shape)
    w = low + rng.uniform(size=c.shape) * (h - low)
    index = pd.MultiIndex.from_product(
        [pd.date_range("2024-01-01", periods=290), list("ABCDEFG")], names=["trade_date", "symbol"]
    )
    return pd.DataFrame(
        {
            k: x.ravel()
            for k, x in dict(
                raw_open=o, raw_close=c, raw_high=h, raw_low=low, volume=v, amount=v * w
            ).items()
        },
        index=index,
    ).reset_index()


def oracle(bars):
    o, c, h, low, v, amount = [
        bars.pivot(index="trade_date", columns="symbol", values=f).to_numpy()
        for f in ["raw_open", "raw_close", "raw_high", "raw_low", "volume", "amount"]
    ]

    def rank(x):
        out = np.full(x.shape, np.nan)
        for i, row in enumerate(x):
            valid = np.isfinite(row)
            if valid.any():
                normalized = np.round(row[valid] / (max(abs(row[valid])) or 1), 12)
                out[i, valid] = rankdata(normalized) / valid.sum()
        return out

    def delay(x, n=1):
        return np.vstack([np.full((n, x.shape[1]), np.nan), x[:-n]])

    def roll(x, n, op):
        windows = np.lib.stride_tricks.sliding_window_view(x, n, axis=0)
        values = op(windows, axis=-1)
        return np.vstack([np.full((n - 1, x.shape[1]), np.nan), values])

    def mean(x, n):
        return roll(x, n, np.mean)

    def total(x, n):
        return roll(x, n, np.sum)

    def corr(x, y, n):
        out = np.full(x.shape, np.nan)
        for i in range(n - 1, len(x)):
            for j in range(x.shape[1]):
                a, b = x[i - n + 1 : i + 1, j], y[i - n + 1 : i + 1, j]
                if np.isfinite(a).all() and np.isfinite(b).all() and np.ptp(a) and np.ptp(b):
                    out[i, j] = np.corrcoef(a, b)[0, 1]
        return out

    def scale(x):
        norm = np.nansum(abs(x), axis=1)[:, None]
        return np.divide(x, norm, out=np.full_like(x, np.nan), where=norm != 0)

    w = amount / v
    r = c / delay(c) - 1
    adv = mean(amount, 20)
    product = total(o, 5) * total(r, 5)
    difference = w - c
    slope = (delay(c, 20) - delay(c, 10)) / 10 - (delay(c, 10) - c) / 10
    m8, m2 = mean(c, 8), mean(c, 2)
    s8 = roll(c, 8, lambda x, axis: np.std(x, axis=axis, ddof=1))
    change = (mean(c, 100) - delay(mean(c, 100), 100)) / delay(c, 100)
    conditions = rank(mean(corr(rank(v), rank(w), 6), 2))
    out = {
        5: rank(o - mean(w, 10)) * -abs(rank(c - w)),
        8: -rank(product - delay(product, 10)),
        11: (rank(roll(difference, 3, np.max)) + rank(roll(difference, 3, np.min)))
        * rank(v - delay(v, 3)),
        19: -np.sign(c - delay(c, 7) + (c - delay(c, 7))) * (1 + rank(1 + total(r, 250))),
        21: np.where(
            m8 + s8 < m2, -1, np.where(m2 < m8 - s8, 1, np.where(v / adv >= 1, 1, -1))
        ).astype(float),
        24: np.where(change <= 0.05, -(c - roll(c, 100, np.min)), -(c - delay(c))),
        25: rank(-r * adv * w * (h - c)),
        27: np.where(conditions > 0.5, -1, 1).astype(float),
        28: scale(corr(adv, low, 5) + (h + low) / 2 - c),
        30: (
            1
            - rank(
                np.sign(c - delay(c))
                + np.sign(delay(c) - delay(c, 2))
                + np.sign(delay(c, 2) - delay(c, 3))
            )
        )
        * total(v, 5)
        / total(v, 20),
        32: scale(mean(c, 7) - c) + 20 * scale(corr(w, delay(c, 5), 230)),
        37: rank(corr(delay(o - c), c, 200)) + rank(o - c),
        41: np.sqrt(h * low) - w,
        42: rank(w - c) / rank(w + c),
        45: -rank(mean(delay(c, 5), 20)) * corr(c, v, 2) * rank(corr(total(c, 5), total(c, 20), 2)),
        46: np.where(slope > 0.25, -1, np.where(slope < 0, 1, -(c - delay(c)))),
        47: rank(1 / c) * v / adv * (h * rank(h - c) / mean(h, 5)) - rank(w - delay(w, 5)),
        49: np.where(slope < -0.1, 1, -(c - delay(c))),
        50: -roll(rank(corr(rank(v), rank(w), 5)), 5, np.max),
        51: np.where(slope < -0.05, 1, -(c - delay(c))),
    }
    # The false branch of #024 uses a three-day, not one-day, price difference.
    out[24] = np.where(change <= 0.05, -(c - roll(c, 100, np.min)), -(c - delay(c, 3)))
    out[24][~np.isfinite(change)] = np.nan
    out[21][~np.isfinite(adv)] = np.nan
    out[27][~np.isfinite(conditions)] = np.nan
    for n in [46, 49, 51]:
        out[n][~np.isfinite(slope)] = np.nan
    return out


def test_all_formulas_against_independent_arrays(market):
    assert [int(f.name[-3:]) for f in batch2_factors()] == NUMBERS
    assert len({f.name for f in alpha101_factors()}) == 82
    expected = oracle(market)
    for factor in batch2_factors():
        actual = factor.compute(market).pivot(index="date", columns="symbol", values="value")
        actual = actual.reindex(index=sorted(market.trade_date.unique()), columns=list("ABCDEFG"))
        np.testing.assert_allclose(
            actual, expected[int(factor.name[-3:])], atol=1e-8, equal_nan=True, err_msg=factor.name
        )


@pytest.mark.parametrize("factor", batch2_factors(), ids=lambda f: f.name)
def test_history_causality_and_required_fields(factor, market):
    dates = sorted(market.trade_date.unique())
    full = factor.compute(market)
    assert not full.empty
    assert full.date.min() >= dates[factor.min_history - 1]
    assert factor.compute(market[market.trade_date < dates[factor.min_history - 1]]).empty
    prefix = factor.compute(market[market.trade_date <= dates[260]])
    pd.testing.assert_frame_equal(prefix, full[full.date <= dates[260]].reset_index(drop=True))
    with pytest.raises(ValueError, match="缺少字段"):
        factor.compute(market.drop(columns=factor.required_fields[-1]))


def test_zero_missing_and_conditional_data(market):
    factors = {int(f.name[-3:]): f for f in batch2_factors()}
    bad = market.copy()
    bad["volume"] = 0
    for n in [5, 11, 25, 27, 32, 41, 42, 47, 50]:
        assert factors[n].compute(bad).empty
    bad = market.copy()
    bad["amount"] = np.nan
    for n in [5, 11, 21, 25, 27, 28, 32, 41, 42, 47, 50]:
        assert factors[n].compute(bad).empty
    # Hand-computed VWAP: 200 yuan / 10 shares = 20, not average OHLC.
    tiny = market.iloc[:7].copy()
    tiny["raw_high"], tiny["raw_low"], tiny["amount"], tiny["volume"] = 25, 16, 200, 10
    np.testing.assert_allclose(factors[41].compute(tiny).value, 0)


@pytest.mark.parametrize(
    "pattern,amount,expected",
    [
        ("up", 2.0, -1),
        ("down", 2.0, 1),
        ("flat", 0.5, 1),
        ("flat", 2.0, -1),
    ],
)
def test_alpha021_all_branches(pattern, amount, expected):
    prices = {
        "up": np.arange(10.0, 30.0),
        "down": np.arange(30.0, 10.0, -1),
        "flat": np.full(20, 20.0),
    }[pattern]
    bars = pd.DataFrame(
        {
            "trade_date": pd.date_range("2025-01-01", periods=20),
            "symbol": "A",
            "raw_close": prices,
            "volume": 1.0,
            "amount": amount,
        }
    )
    factor = next(f for f in batch2_factors() if f.name == "alpha101_021")
    assert factor.compute(bars).value.tolist() == [expected]


def test_two_day_correlation_ties_are_exact():
    from quant_platform.factors.alpha_operators import correlation

    x = pd.DataFrame({"A": [10000.0, 10000.001], "B": [20000.0, 20000.001]})
    y = pd.DataFrame({"A": [100.0, 100.002], "B": [200.0, 199.998]})
    np.testing.assert_array_equal(correlation(x, y, 2).iloc[-1], [1.0, -1.0])


def test_vwap_factor_page_evaluation(market, tmp_path, monkeypatch):
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/9_factor_lab.py"
    monkeypatch.chdir(tmp_path)
    Path("configs").mkdir()
    Path("configs/app.yaml").write_text("data:\n  repository: runtime/market\n", encoding="utf-8")
    ParquetMarketDataRepository("runtime/market").save_table("daily_bars", market)
    app = AppTest.from_file(str(page), default_timeout=30).run()
    app.selectbox(key="factor_eval_name").set_value("alpha101_025")
    app.date_input(key="factor_start").set_value(pd.Timestamp("2024-08-01").date())
    app.date_input(key="factor_end").set_value(pd.Timestamp("2024-10-15").date())
    app.button(key="factor_eval_run").click().run()
    assert not app.exception and not app.error
    assert any(m.label == "Rank IC 均值" and m.value != "nan" for m in app.metric)
