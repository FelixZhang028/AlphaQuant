"""Independent numpy/scipy formula checks and missing-data contracts."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import rankdata
from streamlit.testing.v1 import AppTest

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.alpha101 import alpha101_factors

NUMBERS = [2, 3, 6, 9, 10, 12, 13, 14, 15, 16, 18, 20, 22, 23, 33, 34, 40, 44, 55, 101]


@pytest.fixture
def market():
    rng = np.random.default_rng(724)
    shape = (50, 7)
    close = 30 + rng.normal(size=shape).cumsum(axis=0)
    opening = close + rng.normal(size=shape)
    high = np.maximum(opening, close) + rng.uniform(0.1, 3, shape)
    low = np.minimum(opening, close) - rng.uniform(0.1, 3, shape)
    volume = rng.uniform(100, 10000, shape)
    index = pd.MultiIndex.from_product(
        [pd.date_range("2025-01-01", periods=50), list("ABCDEFG")],
        names=["trade_date", "symbol"],
    )
    return pd.DataFrame(
        dict(
            raw_open=opening.ravel(),
            raw_close=close.ravel(),
            raw_high=high.ravel(),
            raw_low=low.ravel(),
            volume=volume.ravel(),
        ),
        index=index,
    ).reset_index()


def reference(bars):
    """Slow dense oracle; no pandas rolling/rank or production operators."""
    o, c, h, low, v = [
        bars.pivot(index="trade_date", columns="symbol", values=f).to_numpy()
        for f in ["raw_open", "raw_close", "raw_high", "raw_low", "volume"]
    ]

    def rank(x):
        output = np.full(x.shape, np.nan)
        for i, row in enumerate(x):
            mask = np.isfinite(row)
            if mask.any():
                scale = max(abs(row[mask])) or 1.0
                output[i, mask] = rankdata(np.round(row[mask] / scale, 12)) / mask.sum()
        return output

    def delay(x, n=1):
        return np.vstack([np.full((n, x.shape[1]), np.nan), x[:-n]])

    def delta(x, n=1):
        return x - delay(x, n)

    def roll(x, n, fn, y=None):
        out = np.full(x.shape, np.nan)
        for day in range(n - 1, len(x)):
            for stock in range(x.shape[1]):
                a = x[day - n + 1 : day + 1, stock]
                if not np.isfinite(a).all():
                    continue
                if y is None:
                    out[day, stock] = fn(a)
                else:
                    b = y[day - n + 1 : day + 1, stock]
                    if np.isfinite(b).all():
                        out[day, stock] = fn(a, b)
        return out

    def corr(x, y, n):
        return roll(
            x,
            n,
            lambda a, b: np.corrcoef(a, b)[0, 1] if np.ptp(a) > 0 and np.ptp(b) > 0 else np.nan,
            y,
        )

    def std(x, n):
        return roll(x, n, lambda a: np.std(a, ddof=1))

    def conditional(n):
        d = delta(c)
        bottom, top = roll(d, n, np.min), roll(d, n, np.max)
        result = np.where((bottom > 0) | (top < 0), d, -d)
        return np.where(np.isfinite(bottom) & np.isfinite(top), result, np.nan)

    returns = c / delay(c) - 1

    def covariance(x):
        return roll(rank(x), 5, lambda a, b: np.cov(a, b, ddof=1)[0, 1], rank(v))

    bottom, top = roll(low, 12, np.min), roll(h, 12, np.max)
    high_mean = roll(h, 20, np.mean)
    with np.errstate(divide="ignore", invalid="ignore"):
        return {
            2: -corr(rank(delta(np.log(v), 2)), rank((c - o) / o), 6),
            3: -corr(rank(o), rank(v), 10),
            6: -corr(o, v, 10),
            9: conditional(5),
            10: rank(conditional(4)),
            12: np.sign(delta(v)) * -delta(c),
            13: -rank(covariance(c)),
            14: -rank(delta(returns, 3)) * corr(o, v, 10),
            15: -roll(rank(corr(rank(h), rank(v), 3)), 3, np.sum),
            16: -rank(covariance(h)),
            18: -rank(std(abs(c - o), 5) + c - o + corr(c, o, 10)),
            20: -rank(o - delay(h)) * rank(o - delay(c)) * rank(o - delay(low)),
            22: -delta(corr(h, v, 5), 5) * rank(std(c, 20)),
            23: np.where(np.isfinite(high_mean), np.where(high_mean < h, -delta(h, 2), 0), np.nan),
            33: rank(o / c - 1),
            34: rank(2 - rank(std(returns, 2) / std(returns, 5)) - rank(delta(c))),
            40: -rank(std(h, 10)) * corr(h, v, 10),
            44: -corr(h, rank(v), 5),
            55: -corr(rank((c - bottom) / (top - bottom)), rank(v), 6),
            101: (c - o) / (h - low + 0.001),
        }


def test_exact_batch_and_independent_formula_values(market):
    factors = [f for f in alpha101_factors() if int(f.name[-3:]) in NUMBERS]
    assert [int(f.name[-3:]) for f in factors] == NUMBERS
    expected = reference(market)
    dates = sorted(market.trade_date.unique())
    for factor in factors:
        output = factor.compute(market)
        dense = output.pivot(index="date", columns="symbol", values="value").reindex(
            index=dates, columns=list("ABCDEFG")
        )
        np.testing.assert_allclose(
            dense.to_numpy(),
            expected[int(factor.name[-3:])],
            atol=1e-8,
            err_msg=factor.name,
            equal_nan=True,
        )


@pytest.mark.parametrize(
    "factor", [f for f in alpha101_factors() if int(f.name[-3:]) in NUMBERS], ids=lambda f: f.name
)
def test_warmup_and_causal_history(factor, market):
    dates = sorted(market.trade_date.unique())
    full = factor.compute(market)
    assert not full.empty
    assert full.date.min() >= dates[factor.min_history - 1]
    assert factor.compute(market[market.trade_date < dates[factor.min_history - 1]]).empty
    prefix = factor.compute(market[market.trade_date <= dates[30]])
    pd.testing.assert_frame_equal(prefix, full[full.date <= dates[30]].reset_index(drop=True))


def test_undefined_inputs_and_conditional_warmup_are_not_fabricated(market):
    factors = {f.name: f for f in alpha101_factors()}
    # Constant ranks cannot define a correlation; zeros cannot be logged or divided.
    broken = market.copy()
    broken["volume"] = 0.0
    broken["raw_open"] = 0.0
    broken["raw_high"] = broken["raw_low"] = broken["raw_close"] = 10.0
    for number in [2, 3, 6, 14, 15, 18, 22, 34, 40, 44, 55]:
        assert factors[f"alpha101_{number:03d}"].compute(broken).empty
    missing = market.copy()
    missing.loc[(missing.symbol == "A") & (missing.trade_date == "2025-01-25"), "raw_close"] = (
        np.nan
    )
    for number, days in [(9, 6), (10, 5)]:
        result = factors[f"alpha101_{number:03d}"].compute(missing)
        assert result[
            (result.symbol == "A")
            & result.date.between(
                "2025-01-25", pd.Timestamp("2025-01-25") + pd.Timedelta(days=days - 1)
            )
        ].empty


def test_new_factor_can_be_evaluated_in_page(market, tmp_path, monkeypatch):
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/9_factor_lab.py"
    monkeypatch.chdir(tmp_path)
    Path("configs").mkdir()
    Path("configs/app.yaml").write_text("data:\n  repository: runtime/market\n", encoding="utf-8")
    ParquetMarketDataRepository("runtime/market").save_table("daily_bars", market)
    app = AppTest.from_file(str(page), default_timeout=20).run()
    app.selectbox(key="factor_eval_name").set_value("alpha101_055")
    app.date_input(key="factor_start").set_value(pd.Timestamp("2025-01-20").date())
    app.date_input(key="factor_end").set_value(pd.Timestamp("2025-02-19").date())
    app.button(key="factor_eval_run").click().run()
    assert not app.exception
    assert not app.error
    assert any(m.label == "Rank IC 均值" and m.value != "nan" for m in app.metric)
