"""Independent formulas and boundary contracts for rolling-rank alphas."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.stats import rankdata
from streamlit.testing.v1 import AppTest
from test_alpha101_batch2 import market  # noqa: F401

from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.alpha101_batch3 import batch3_factors
from quant_platform.factors.alpha_operators import decay_linear, ts_argmax, ts_rank, window_days

NUMBERS = [1, 4, 7, 17, 26, 31, 35, 36, 38, 39, 43, 52, 53, 54, 57, 60, 61, 64, 65, 75]


def reference(bars):
    o, c, h, low, v, amount = [
        bars.pivot(index="trade_date", columns="symbol", values=k).to_numpy()
        for k in ["raw_open", "raw_close", "raw_high", "raw_low", "volume", "amount"]
    ]

    def rank(x):
        out = np.full(x.shape, np.nan)
        for i, row in enumerate(x):
            mask = np.isfinite(row)
            if mask.any():
                out[i, mask] = (
                    rankdata(np.round(row[mask] / (max(abs(row[mask])) or 1), 12)) / mask.sum()
                )
        return out

    def shift(x, n=1):
        return np.vstack([np.full((n, x.shape[1]), np.nan), x[:-n]])

    def delta(x, n=1):
        return x - shift(x, n)

    def rolling(x, n, fn):
        out = np.full(x.shape, np.nan)
        n = int(n)
        for i in range(n - 1, len(x)):
            for j in range(x.shape[1]):
                a = x[i - n + 1 : i + 1, j]
                if np.isfinite(a).all():
                    out[i, j] = fn(a)
        return out

    def total(x, n):
        return rolling(x, n, np.sum)

    def mean(x, n):
        return rolling(x, n, np.mean)

    def tr(x, n):
        return rolling(x, n, lambda a: rankdata(a)[-1])

    def decay(x, n):
        return rolling(
            x, n, lambda a: sum((k + 1) * z for k, z in enumerate(a)) / (n * (n + 1) / 2)
        )

    def argmax(x, n):
        return rolling(x, n, lambda a: list(a).index(max(a)) + 1)

    def corr(x, y, n):
        n = int(n)
        out = np.full(x.shape, np.nan)
        for i in range(n - 1, len(x)):
            for j in range(x.shape[1]):
                a, b = x[i - n + 1 : i + 1, j], y[i - n + 1 : i + 1, j]
                if (
                    np.isfinite(a).all()
                    and np.isfinite(b).all()
                    and np.ptp(a) > 0
                    and np.ptp(b) > 0
                ):
                    out[i, j] = np.corrcoef(a, b)[0, 1]
        return out

    def scale(x):
        norm = np.nansum(abs(x), axis=1)[:, None]
        return np.divide(x, norm, out=np.full_like(x, np.nan), where=norm != 0)

    def less(x, y):
        return np.where(np.isfinite(x) & np.isfinite(y), (x < y).astype(float), np.nan)

    w = amount / v
    r = c / shift(c) - 1
    adv = mean(amount, 20)
    std = rolling(r, 20, lambda a: np.std(a, ddof=1))
    x = np.where(r < 0, std, c)
    x[~np.isfinite(std)] = np.nan
    d7 = delta(c, 7)
    ranked = tr(abs(d7), 60)
    minimum = rolling(low, 5, np.min)
    with np.errstate(divide="ignore", invalid="ignore"):
        values = {
            1: rank(argmax(x**2, 5)) - 0.5,
            4: -tr(rank(low), 9),
            7: np.where(adv < v, -ranked * np.sign(d7), -1),
            17: -rank(tr(c, 10)) * rank(delta(delta(c))) * rank(tr(v / adv, 5)),
            26: -rolling(corr(tr(v, 5), tr(h, 5), 5), 3, np.max),
            31: rank(rank(rank(decay(-rank(rank(delta(c, 10))), 10))))
            + rank(-delta(c, 3))
            + np.sign(scale(corr(adv, low, 12))),
            35: tr(v, 32) * (1 - tr(c + h - low, 16)) * (1 - tr(r, 32)),
            36: 2.21 * rank(corr(c - o, shift(v), 15))
            + 0.7 * rank(o - c)
            + 0.73 * rank(tr(shift(-r, 6), 5))
            + rank(abs(corr(w, adv, 6)))
            + 0.6 * rank((mean(c, 200) - o) * (c - o)),
            38: -rank(tr(c, 10)) * rank(c / o),
            39: -rank(delta(c, 7) * (1 - rank(decay(v / adv, 9)))) * (1 + rank(total(r, 250))),
            43: tr(v / adv, 20) * tr(-delta(c, 7), 8),
            52: (-minimum + shift(minimum, 5))
            * rank((total(r, 240) - total(r, 20)) / 220)
            * tr(v, 5),
            53: -delta(((c - low) - (h - c)) / (c - low), 9),
            54: -((low - c) * o**5) / ((low - h) * c**5),
            57: -(c - w) / decay(rank(argmax(c, 30)), 2),
            60: -(
                2 * scale(rank(((c - low) - (h - c)) / (h - low) * v)) - scale(rank(argmax(c, 10)))
            ),
            61: less(
                rank(w - rolling(w, 16.1219, np.min)), rank(corr(w, mean(amount, 180), 17.9282))
            ),
            64: -less(
                rank(
                    corr(
                        total(o * 0.178404 + low * (1 - 0.178404), 12),
                        total(mean(amount, 120), 12),
                        16,
                    )
                ),
                rank(delta((h + low) / 2 * 0.178404 + w * (1 - 0.178404), 3)),
            ),
            65: -less(
                rank(corr(o * 0.00817205 + w * (1 - 0.00817205), total(mean(amount, 60), 8), 6)),
                rank(o - rolling(o, 13, np.min)),
            ),
            75: less(rank(corr(w, v, 4)), rank(corr(rank(low), rank(mean(amount, 50)), 12))),
        }
    values[7][~np.isfinite(ranked) | ~np.isfinite(adv)] = np.nan
    return values


def test_formula_reference_and_exact_registry(market):  # noqa: F811
    assert [int(f.name[-3:]) for f in batch3_factors()] == NUMBERS
    assert len({f.name for f in alpha101_factors()}) == 82
    expected = reference(market)
    for f in batch3_factors():
        actual = f.compute(market).pivot(index="date", columns="symbol", values="value")
        actual = actual.reindex(index=sorted(market.trade_date.unique()), columns=list("ABCDEFG"))
        np.testing.assert_allclose(
            actual, expected[int(f.name[-3:])], atol=1e-8, equal_nan=True, err_msg=f.name
        )


@pytest.mark.parametrize("factor", batch3_factors(), ids=lambda f: f.name)
def test_warmup_missing_fields_and_no_future(factor, market):  # noqa: F811
    dates = sorted(market.trade_date.unique())
    full = factor.compute(market)
    assert not full.empty and np.isfinite(full.value).all()
    assert full.date.min() >= dates[factor.min_history - 1]
    assert factor.compute(market[market.trade_date < dates[factor.min_history - 1]]).empty
    prefix = factor.compute(market[market.trade_date <= dates[260]])
    pd.testing.assert_frame_equal(prefix, full[full.date <= dates[260]].reset_index(drop=True))
    with pytest.raises(ValueError, match="缺少字段"):
        factor.compute(market.drop(columns=factor.required_fields[-1]))


def test_operator_conventions_and_missing_windows():
    x = pd.DataFrame({"A": [1.0, 3.0, 3.0, 2.0, np.nan, 5.0, 6.0, 7.0]})
    assert ts_rank(x, 3).iloc[2, 0] == 2.5
    assert ts_rank(x, 3).iloc[3, 0] == 1
    assert ts_argmax(x, 3).iloc[2, 0] == 2
    assert ts_argmax(x, 3).iloc[3, 0] == 1
    assert decay_linear(x, 3).iloc[2, 0] == pytest.approx(16 / 6)
    assert decay_linear(x, 3).iloc[4:7].isna().all().all()
    pd.testing.assert_frame_equal(ts_rank(x, 3.9), ts_rank(x, 3))
    assert window_days(17.9282) == 17
    with pytest.raises(ValueError):
        window_days(0.99)


def test_invalid_inputs_do_not_become_comparison_signals(market):  # noqa: F811
    factors = {int(f.name[-3:]): f for f in batch3_factors()}
    bad = market.copy()
    bad["amount"] = np.nan
    for n in [7, 17, 31, 36, 39, 43, 57, 61, 64, 65, 75]:
        assert factors[n].compute(bad).empty
    bad = market.copy()
    bad["raw_close"] = bad["raw_low"] = bad["raw_high"] = 10.0
    for n in [53, 54, 60]:
        assert factors[n].compute(bad).empty
    bad = market.copy()
    bad["volume"] = 0.0
    for n in [36, 57, 61, 64, 65, 75]:
        assert factors[n].compute(bad).empty


def test_new_decay_factor_page_evaluation(market, tmp_path, monkeypatch):  # noqa: F811
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/9_factor_lab.py"
    monkeypatch.chdir(tmp_path)
    Path("configs").mkdir()
    Path("configs/app.yaml").write_text("data:\n  repository: runtime/market\n", encoding="utf-8")
    ParquetMarketDataRepository("runtime/market").save_table("daily_bars", market)
    app = AppTest.from_file(str(page), default_timeout=30).run()
    app.selectbox(key="factor_eval_name").set_value("alpha101_057")
    app.date_input(key="factor_start").set_value(pd.Timestamp("2024-08-01").date())
    app.date_input(key="factor_end").set_value(pd.Timestamp("2024-10-15").date())
    app.button(key="factor_eval_run").click().run()
    assert not app.exception and not app.error
    assert any(m.label == "Rank IC 均值" and m.value != "nan" for m in app.metric)
