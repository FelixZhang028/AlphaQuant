"""Independent array reference for the final price-volume formulas."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import rankdata
from streamlit.testing.v1 import AppTest

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.alpha101_batch4 import batch4_factors
from quant_platform.factors.alpha_operators import ts_argmin

NUMBERS = [29, 62, 66, 68, 71, 72, 73, 74, 77, 78, 81, 83, 84, 85, 86, 88, 92, 94, 95, 96, 98, 99]


@pytest.fixture(scope="module")
def market():
    rng = np.random.default_rng(9804)
    c = rng.uniform(30, 60, (360, 7))
    o = c + rng.normal(size=c.shape)
    h = np.maximum(o, c) + rng.uniform(0.1, 2, c.shape)
    low = np.minimum(o, c) - rng.uniform(0.1, 2, c.shape)
    v = rng.uniform(100, 5000, c.shape)
    w = low + rng.uniform(size=c.shape) * (h - low)
    index = pd.MultiIndex.from_product(
        [pd.date_range("2024-01-01", periods=360), list("ABCDEFG")], names=["trade_date", "symbol"]
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


def reference(bars):
    o, c, h, low, v, a = [
        bars.pivot(index="trade_date", columns="symbol", values=k).to_numpy()
        for k in ["raw_open", "raw_close", "raw_high", "raw_low", "volume", "amount"]
    ]

    def rank(x):
        result = np.full(x.shape, np.nan)
        for i, row in enumerate(x):
            mask = np.isfinite(row)
            if mask.any():
                result[i, mask] = (
                    rankdata(np.round(row[mask] / (max(abs(row[mask])) or 1), 12)) / mask.sum()
                )
        return result

    def rolling(x, n, fn):
        n = int(n)
        result = np.full(x.shape, np.nan)
        for i in range(n - 1, len(x)):
            for j in range(x.shape[1]):
                chunk = x[i - n + 1 : i + 1, j]
                if np.isfinite(chunk).all():
                    result[i, j] = fn(chunk)
        return result

    def shift(x, n=1):
        return np.vstack([np.full((int(n), x.shape[1]), np.nan), x[: -int(n)]])

    def delta(x, n):
        return x - shift(x, n)

    def total(x, n):
        return rolling(x, n, np.sum)

    def mean(x, n):
        return rolling(x, n, np.mean)

    def mn(x, n):
        return rolling(x, n, np.min)

    def mx(x, n):
        return rolling(x, n, np.max)

    def tr(x, n):
        return rolling(x, n, lambda z: rankdata(np.round(z / (max(abs(z)) or 1), 12))[-1])

    def decay(x, n):
        weights = np.arange(1, int(n) + 1, dtype=float)
        weights /= weights.sum()
        return rolling(x, n, lambda z: np.dot(z, weights))

    def argmax(x, n):
        return rolling(x, n, lambda z: np.argmax(np.round(z / (max(abs(z)) or 1), 12)) + 1)

    def argmin(x, n):
        return rolling(x, n, lambda z: np.argmin(np.round(z / (max(abs(z)) or 1), 12)) + 1)

    def power(x, y):
        return np.where(np.isfinite(x) & np.isfinite(y), np.power(x, y), np.nan)

    def corr(x, y, n):
        n = int(n)
        result = np.full(x.shape, np.nan)
        for i in range(n - 1, len(x)):
            for j in range(x.shape[1]):
                xx, yy = x[i - n + 1 : i + 1, j], y[i - n + 1 : i + 1, j]
                if (
                    np.isfinite(xx).all()
                    and np.isfinite(yy).all()
                    and np.ptp(xx) > 0
                    and np.ptp(yy) > 0
                ):
                    result[i, j] = np.corrcoef(xx, yy)[0, 1]
        return result

    def less(x, y):
        return np.where(np.isfinite(x) & np.isfinite(y), (x < y).astype(float), np.nan)

    def scale(x):
        norm = np.nansum(abs(x), axis=1)[:, None]
        return np.divide(x, norm, out=np.full_like(x, np.nan), where=norm != 0)

    w = a / v
    adv = {n: mean(a, n) for n in [5, 10, 15, 20, 30, 40, 60, 180]}
    with np.errstate(divide="ignore", invalid="ignore"):
        ret = c / shift(c) - 1
        x = mn(rank(rank(-rank(delta(c - 1, 5)))), 2)
        x = rank(rank(scale(np.log(total(x, 1)))))
        position = (h - low) / mean(c, 5)
        mixed = o * 0.147155 + low * (1 - 0.147155)
        return {
            29: mn(rolling(x, 1, np.prod), 5) + tr(shift(-ret, 6), 5),
            62: -less(
                rank(corr(w, total(adv[20], 22), 9)),
                rank(less(rank(o) + rank(o), rank((h + low) / 2) + rank(h))),
            ),
            66: -(
                rank(decay(delta(w, 3), 7))
                + tr(decay((low * 0.96633 + low * (1 - 0.96633) - w) / (o - (h + low) / 2), 11), 6)
            ),
            68: -less(
                tr(corr(rank(h), rank(adv[15]), 8), 13),
                rank(delta(c * 0.518371 + low * (1 - 0.518371), 1)),
            ),
            71: np.maximum(
                tr(decay(corr(tr(c, 3), tr(adv[180], 12), 18), 4), 15),
                tr(decay(rank(low + o - 2 * w) ** 2, 16), 4),
            ),
            72: rank(decay(corr((h + low) / 2, adv[40], 8), 10))
            / rank(decay(corr(tr(w, 3), tr(v, 18), 6), 2)),
            73: -np.maximum(
                rank(decay(delta(w, 4), 2)), tr(decay(-delta(mixed, 2) / mixed, 3), 16)
            ),
            74: -less(
                rank(corr(c, total(adv[30], 37), 15)),
                rank(corr(rank(h * 0.0261661 + w * (1 - 0.0261661)), rank(v), 11)),
            ),
            77: np.minimum(
                rank(decay((h + low) / 2 + h - (w + h), 20)),
                rank(decay(corr((h + low) / 2, adv[40], 3), 5)),
            ),
            78: power(
                rank(corr(total(low * 0.352233 + w * (1 - 0.352233), 19), total(adv[40], 19), 6)),
                rank(corr(rank(w), rank(v), 5)),
            ),
            81: -less(
                rank(np.log(rolling(rank(rank(corr(w, total(adv[10], 49), 8)) ** 4), 14, np.prod))),
                rank(corr(rank(w), rank(v), 5)),
            ),
            83: rank(shift(position, 2)) * rank(rank(v)) / (position / (w - c)),
            84: power(tr(w - mx(w, 15), 20), delta(c, 4)),
            85: power(
                rank(corr(h * 0.876703 + c * (1 - 0.876703), adv[30], 9)),
                rank(corr(tr((h + low) / 2, 3), tr(v, 10), 7)),
            ),
            86: -less(tr(corr(c, total(adv[20], 14), 6), 20), rank(o + c - (w + o))),
            88: np.minimum(
                rank(decay(rank(o) + rank(low) - rank(h) - rank(c), 8)),
                tr(decay(corr(tr(c, 8), tr(adv[60], 20), 8), 6), 2),
            ),
            92: np.minimum(
                tr(decay(less((h + low) / 2 + c, low + o), 14), 18),
                tr(decay(corr(rank(low), rank(adv[30]), 7), 6), 6),
            ),
            94: -power(rank(w - mn(w, 11)), tr(corr(tr(w, 19), tr(adv[60], 4), 18), 2)),
            95: less(
                rank(o - mn(o, 12)),
                tr(rank(corr(total((h + low) / 2, 19), total(adv[40], 19), 12)) ** 5, 11),
            ),
            96: -np.maximum(
                tr(decay(corr(rank(w), rank(v), 3), 4), 8),
                tr(decay(argmax(corr(tr(c, 7), tr(adv[60], 4), 3), 12), 14), 13),
            ),
            98: rank(decay(corr(w, total(adv[5], 26), 4), 7))
            - rank(decay(tr(argmin(corr(rank(o), rank(adv[15]), 20), 8), 6), 8)),
            99: -less(
                rank(corr(total((h + low) / 2, 19), total(adv[60], 19), 8)), rank(corr(low, v, 6))
            ),
        }


def test_all_formulas_and_remaining_industry_set(market):  # noqa: F811
    assert [int(f.name[-3:]) for f in batch4_factors()] == NUMBERS
    all_numbers = {int(f.name[-3:]) for f in alpha101_factors()}
    assert len(all_numbers) == 82
    for factor in alpha101_factors():
        assert factor.formula.count("(") == factor.formula.count(")"), factor.name
    assert set(range(1, 102)) - all_numbers == {
        48,
        56,
        58,
        59,
        63,
        67,
        69,
        70,
        76,
        79,
        80,
        82,
        87,
        89,
        90,
        91,
        93,
        97,
        100,
    }
    expected = reference(market)
    for f in batch4_factors():
        actual = f.compute(market).pivot(index="date", columns="symbol", values="value")
        actual = actual.reindex(index=sorted(market.trade_date.unique()), columns=list("ABCDEFG"))
        np.testing.assert_allclose(
            actual, expected[int(f.name[-3:])], atol=1e-8, equal_nan=True, err_msg=f.name
        )


@pytest.mark.parametrize("factor", batch4_factors(), ids=lambda f: f.name)
def test_history_and_future_independence(factor, market):  # noqa: F811
    dates = sorted(market.trade_date.unique())
    result = factor.compute(market)
    assert not result.empty and np.isfinite(result.value).all()
    assert result.date.min() >= dates[factor.min_history - 1]
    assert factor.compute(market[market.trade_date < dates[factor.min_history - 1]]).empty
    prefix = factor.compute(market[market.trade_date <= dates[260]])
    pd.testing.assert_frame_equal(prefix, result[result.date <= dates[260]].reset_index(drop=True))
    with pytest.raises(ValueError, match="缺少字段"):
        factor.compute(market.drop(columns=factor.required_fields[-1]))


def test_missing_inputs_zero_denominators_and_argmin(market):  # noqa: F811
    for f in batch4_factors():
        bad = market.copy()
        bad[f.required_fields[-1]] = np.nan
        assert f.compute(bad).empty, f.name
    factors = {int(f.name[-3:]): f for f in batch4_factors()}
    bad = market.copy()
    bad["raw_open"] = (bad.raw_high + bad.raw_low) / 2
    assert factors[66].compute(bad).empty
    bad = market.copy()
    bad["amount"] = bad.volume * bad.raw_close
    assert factors[83].compute(bad).empty
    x = pd.DataFrame({"A": [2.0, 1.0, 1.0, np.nan, 3.0]})
    assert ts_argmin(x, 3.9).iloc[2, 0] == 2
    assert ts_argmin(x, 3).iloc[3:].isna().all().all()


def test_batch4_page_evaluation(market, tmp_path, monkeypatch):  # noqa: F811
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/9_factor_lab.py"
    monkeypatch.chdir(tmp_path)
    Path("configs").mkdir()
    Path("configs/app.yaml").write_text("data:\n  repository: runtime/market\n", encoding="utf-8")
    ParquetMarketDataRepository("runtime/market").save_table("daily_bars", market)
    app = AppTest.from_file(str(page), default_timeout=30).run()
    app.selectbox(key="factor_eval_name").set_value("alpha101_098")
    app.date_input(key="factor_start").set_value(pd.Timestamp("2024-08-01").date())
    app.date_input(key="factor_end").set_value(pd.Timestamp("2024-10-15").date())
    app.button(key="factor_eval_run").click().run()
    assert not app.exception and not app.error
    assert any(m.label == "Rank IC 均值" and m.value != "nan" for m in app.metric)
