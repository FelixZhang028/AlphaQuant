"""Alpha101 subset: every formula against a day-by-day reference written from the paper."""
import math

import numpy as np
import pandas as pd
import pytest

from quant_platform.factors import alpha101
from quant_platform.factors.alpha101 import FORMULAS, Panel, alpha101_factors
from quant_platform.factors.registry import default_registry

DAYS, STOCKS = 45, 7
NAN = float("nan")


def make_bars(seed=7, adj=None):
    """A small random market. ``adj`` maps (symbol index, day index) -> factor from that day on."""

    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-02", periods=DAYS)
    rows = []
    for s in range(STOCKS):
        # 价格水平互相交叉：这样价格的截面排名每天都在变，排名类公式才有可比较的值。
        close = 20 + 0.2 * s + np.cumsum(rng.normal(0, 0.6, DAYS))
        factor = np.ones(DAYS)
        for (stock, day), value in (adj or {}).items():
            if stock == s:
                factor[day:] = value
        for t, day in enumerate(dates):
            spread = abs(rng.normal(0.3, 0.1)) + 0.05
            high, low = close[t] + spread, close[t] - spread
            open_ = low + rng.uniform(0.1, 0.9) * (high - low)
            volume = float(rng.integers(5_000, 90_000)) + rng.uniform(0, 1)
            vwap = low + rng.uniform(0.2, 0.8) * (high - low)
            rows.append({"symbol": f"S{s}", "trade_date": day, "raw_open": open_, "raw_high": high, "raw_low": low,
                         "raw_close": close[t], "volume": volume, "amount": vwap * volume,
                         "adj_factor": factor[t], "adjusted_close": close[t] * factor[t]})
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Reference operators: plain loops over numpy arrays shaped [day, stock].
# --------------------------------------------------------------------------- #


def r_rank(x):
    out = np.full(x.shape, NAN)
    for t in range(x.shape[0]):
        valid = [v for v in x[t] if not math.isnan(v)]
        for s in range(x.shape[1]):
            v = x[t, s]
            if not math.isnan(v):
                out[t, s] = (sum(w < v for w in valid) + (sum(w == v for w in valid) + 1) / 2) / len(valid)
    return out


def r_window(x, d, fn):
    out = np.full(x.shape, NAN)
    for s in range(x.shape[1]):
        for t in range(d - 1, x.shape[0]):
            window = x[t - d + 1:t + 1, s]
            if not np.isnan(window).any():
                out[t, s] = fn(window)
    return out


def r_pair(x, y, d, fn):
    out = np.full(x.shape, NAN)
    for s in range(x.shape[1]):
        for t in range(d - 1, x.shape[0]):
            a, b = x[t - d + 1:t + 1, s], y[t - d + 1:t + 1, s]
            if not (np.isnan(a).any() or np.isnan(b).any()):
                out[t, s] = fn(a, b)
    return out


def r_delay(x, d):
    out = np.full(x.shape, NAN)
    out[d:] = x[:-d]
    return out


def _corr(a, b):
    flat = a.max() == a.min() or b.max() == b.min()
    return NAN if flat else round(float(np.corrcoef(a, b)[0, 1]), alpha101.MOMENT_DECIMALS)


def _cov(a, b):
    flat = a.max() == a.min() or b.max() == b.min()
    return 0.0 if flat else round(float(np.cov(a, b, ddof=1)[0, 1]), alpha101.MOMENT_DECIMALS)


r_delta = lambda x, d: x - r_delay(x, d)  # noqa: E731
r_sum = lambda x, d: r_window(x, d, np.sum)  # noqa: E731
r_min = lambda x, d: r_window(x, d, np.min)  # noqa: E731
r_max = lambda x, d: r_window(x, d, np.max)  # noqa: E731
r_std = lambda x, d: r_window(x, d, lambda w: float(np.std(w, ddof=1)))  # noqa: E731
r_ts_rank = lambda x, d: r_window(x, d, lambda w: (np.sum(w < w[-1]) + (np.sum(w == w[-1]) + 1) / 2) / len(w))  # noqa: E731
r_corr = lambda x, y, d: r_pair(x, y, d, _corr)  # noqa: E731
r_cov = lambda x, y, d: r_pair(x, y, d, _cov)  # noqa: E731


def where(condition, yes, no):
    return np.where(condition, yes, no)


def r_trend(c, d):
    change = r_delta(c, 1)
    lowest, highest = r_min(change, d), r_max(change, d)
    return where(np.isnan(lowest), NAN, where((lowest > 0) | (highest < 0), change, -change))


def r_alpha023(h):
    average = r_sum(h, 20) / 20
    return where(np.isnan(average), NAN, where(average < h, -r_delta(h, 2), 0.0))


def r_alpha030(c, v):
    streak = np.sign(c - r_delay(c, 1)) + np.sign(r_delay(c, 1) - r_delay(c, 2)) + np.sign(r_delay(c, 2) - r_delay(c, 3))
    return (1.0 - r_rank(streak)) * r_sum(v, 5) / r_sum(v, 20)


# number -> the paper's expression, written again with the reference operators.
# o, h, l, c, v: raw open/high/low/close/volume; w: vwap; r: returns; a20: adv20.
REFERENCE = {
    2: lambda o, h, l, c, v, w, r, a20: -r_corr(r_rank(r_delta(np.log(v), 2)), r_rank((c - o) / o), 6),
    3: lambda o, h, l, c, v, w, r, a20: -r_corr(r_rank(o), r_rank(v), 10),
    4: lambda o, h, l, c, v, w, r, a20: -r_ts_rank(r_rank(l), 9),
    5: lambda o, h, l, c, v, w, r, a20: r_rank(o - r_sum(w, 10) / 10) * (-np.abs(r_rank(c - w))),
    6: lambda o, h, l, c, v, w, r, a20: -r_corr(o, v, 10),
    9: lambda o, h, l, c, v, w, r, a20: r_trend(c, 5),
    10: lambda o, h, l, c, v, w, r, a20: r_rank(r_trend(c, 4)),
    11: lambda o, h, l, c, v, w, r, a20: (r_rank(r_max(w - c, 3)) + r_rank(r_min(w - c, 3))) * r_rank(r_delta(v, 3)),
    12: lambda o, h, l, c, v, w, r, a20: np.sign(r_delta(v, 1)) * (-1 * r_delta(c, 1)),
    13: lambda o, h, l, c, v, w, r, a20: -r_rank(r_cov(r_rank(c), r_rank(v), 5)),
    14: lambda o, h, l, c, v, w, r, a20: (-r_rank(r_delta(r, 3))) * r_corr(o, v, 10),
    15: lambda o, h, l, c, v, w, r, a20: -r_sum(r_rank(r_corr(r_rank(h), r_rank(v), 3)), 3),
    16: lambda o, h, l, c, v, w, r, a20: -r_rank(r_cov(r_rank(h), r_rank(v), 5)),
    18: lambda o, h, l, c, v, w, r, a20: -r_rank(r_std(np.abs(c - o), 5) + (c - o) + r_corr(c, o, 10)),
    20: lambda o, h, l, c, v, w, r, a20: (-r_rank(o - r_delay(h, 1))) * r_rank(o - r_delay(c, 1)) * r_rank(o - r_delay(l, 1)),
    23: lambda o, h, l, c, v, w, r, a20: r_alpha023(h),
    25: lambda o, h, l, c, v, w, r, a20: r_rank(((-1 * r) * a20) * w * (h - c)),
    30: lambda o, h, l, c, v, w, r, a20: r_alpha030(c, v),
    33: lambda o, h, l, c, v, w, r, a20: r_rank(-1 * (1 - o / c)),
    34: lambda o, h, l, c, v, w, r, a20: r_rank((1 - r_rank(r_std(r, 2) / r_std(r, 5))) + (1 - r_rank(r_delta(c, 1)))),
    38: lambda o, h, l, c, v, w, r, a20: (-r_rank(r_ts_rank(c, 10))) * r_rank(c / o),
    40: lambda o, h, l, c, v, w, r, a20: (-r_rank(r_std(h, 10))) * r_corr(h, v, 10),
    41: lambda o, h, l, c, v, w, r, a20: (h * l) ** 0.5 - w,
    42: lambda o, h, l, c, v, w, r, a20: r_rank(w - c) / r_rank(w + c),
    44: lambda o, h, l, c, v, w, r, a20: -r_corr(h, r_rank(v), 5),
    53: lambda o, h, l, c, v, w, r, a20: -r_delta(((c - l) - (h - c)) / (c - l), 9),
    54: lambda o, h, l, c, v, w, r, a20: (-1 * ((l - c) * o**5)) / ((l - h) * c**5),
    101: lambda o, h, l, c, v, w, r, a20: (c - o) / ((h - l) + 0.001),
}


def inputs(bars):
    wide = lambda name: bars.pivot(index="trade_date", columns="symbol", values=name).to_numpy()  # noqa: E731
    o, h, l, c, v, amount = (wide(name) for name in ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "amount"))
    adjusted = wide("adjusted_close")
    returns = np.full(c.shape, NAN)
    returns[1:] = adjusted[1:] / adjusted[:-1] - 1
    return o, h, l, c, v, amount / v, returns, r_window(amount, 20, np.mean)


def computed(bars, number):
    factor = next(f for f in alpha101_factors() if f.name == f"alpha101_{number:03d}")
    return factor.compute(bars).pivot(index="date", columns="symbol", values="value").reindex(
        index=sorted(bars["trade_date"].unique()), columns=sorted(bars["symbol"].unique())).to_numpy()


def test_every_formula_has_a_reference_and_the_library_lists_them_all():
    assert sorted(REFERENCE) == [item.number for item in FORMULAS]
    assert len(FORMULAS) == 28 == len({item.number for item in FORMULAS})
    registered = {f.name: f for f in default_registry().list() if f.source == "Alpha101"}
    assert sorted(registered) == [f"alpha101_{item.number:03d}" for item in FORMULAS]
    assert all(f.direction == 1 and f.source_url.endswith("1601.00991") and f.formula for f in registered.values())


@pytest.mark.parametrize("number", sorted(REFERENCE))
def test_formula_matches_the_day_by_day_reference(number):
    bars = make_bars()
    expected = REFERENCE[number](*inputs(bars))
    expected = np.where(np.isinf(expected), NAN, expected)
    actual = computed(bars, number)
    assert np.isfinite(actual).sum() > DAYS, "the formula should produce values on this market"
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-9, equal_nan=True)


@pytest.mark.parametrize("item", FORMULAS, ids=lambda item: f"alpha{item.number:03d}")
def test_the_first_value_appears_exactly_when_the_declared_history_is_available(item):
    values = computed(make_bars(), item.number)
    first = next(t for t in range(DAYS) if np.isfinite(values[t]).any())
    assert first == item.history - 1


def test_hand_checked_values_on_a_two_stock_day():
    bars = pd.DataFrame([
        {"symbol": "A", "trade_date": "2025-01-02", "raw_open": 10.0, "raw_high": 12.0, "raw_low": 9.0, "raw_close": 11.0, "volume": 100.0, "amount": 1050.0},
        {"symbol": "B", "trade_date": "2025-01-02", "raw_open": 20.0, "raw_high": 20.0, "raw_low": 16.0, "raw_close": 18.0, "volume": 200.0, "amount": 3600.0},
    ])
    value = lambda number: dict(zip(*(lambda f: (f["symbol"], f["value"]))(  # noqa: E731
        next(f for f in alpha101_factors() if f.name == f"alpha101_{number:03d}").compute(bars))))
    # 101: (close - open) / (high - low + 0.001)
    assert value(101) == pytest.approx({"A": 1 / 3.001, "B": -2 / 4.001})
    # 41: sqrt(high * low) - vwap, vwap = amount / volume = 10.5 and 18
    assert value(41) == pytest.approx({"A": math.sqrt(108) - 10.5, "B": math.sqrt(320) - 18})
    # 54: -((low - close) * open^5) / ((low - high) * close^5)
    assert value(54) == pytest.approx({"A": -((-2) * 10**5) / ((-3) * 11**5), "B": -((-2) * 20**5) / ((-4) * 18**5)})
    # 33: rank(open / close - 1): A = -0.0909 (lower), B = +0.1111 (higher)
    assert value(33) == pytest.approx({"A": 0.5, "B": 1.0})
    # 42: rank(vwap - close) / rank(vwap + close): differences -0.5 and 0, sums 21.5 and 36
    assert value(42) == pytest.approx({"A": 1.0, "B": 1.0})


def test_returns_are_true_returns_and_a_window_across_an_ex_date_stays_missing():
    # 第 3 只股票在第 30 天除权：之前的复权因子是 0.5，从这一天起是 1（相当于 10 送 10）。
    plain = make_bars()
    split = make_bars(adj={(3, 0): 0.5, (3, 30): 1.0})
    ex_day = 30
    halved = split["symbol"].eq("S3") & (split["trade_date"] >= pd.bdate_range("2025-01-02", periods=DAYS)[ex_day])
    for column in ("raw_open", "raw_high", "raw_low", "raw_close"):
        split.loc[halved, column] /= 2
    split.loc[halved, "volume"] *= 2
    split["adjusted_close"] = split["raw_close"] * split["adj_factor"]

    # 收益率不把除权当成下跌。
    np.testing.assert_allclose(Panel(split).returns.to_numpy(), Panel(plain).returns.to_numpy(), rtol=1e-9, equal_nan=True)

    for item in FORMULAS:
        values = computed(split, item.number)[:, 3]
        reference = computed(plain, item.number)[:, 3]
        blank = slice(ex_day, ex_day + item.span)
        assert np.isnan(values[blank]).all(), f"alpha {item.number}: the window across the ex-date must be missing"
        if item.span and ex_day + item.span < DAYS:
            assert np.isfinite(values[ex_day + item.span:]).any(), f"alpha {item.number}: values return after the window"
        # 除权之前的值不受以后的除权影响（没有未来数据）。
        np.testing.assert_allclose(values[:ex_day], reference[:ex_day], rtol=1e-9, equal_nan=True)


def test_small_factor_noise_is_not_treated_as_a_corporate_action():
    noisy = make_bars(adj={(2, 20): 1 + alpha101.ACTION_THRESHOLD / 2})
    assert np.isfinite(computed(noisy, 6)[20:30, 2]).all()


def test_missing_adjustment_data_and_suspended_days_do_not_break_the_formulas():
    bars = make_bars().drop(columns=["adj_factor", "adjusted_close"])
    suspended = bars["symbol"].eq("S1") & bars["trade_date"].eq(pd.bdate_range("2025-01-02", periods=DAYS)[25])
    bars.loc[suspended, ["volume", "amount"]] = 0.0
    for item in FORMULAS:
        frame = next(f for f in alpha101_factors() if f.name == f"alpha101_{item.number:03d}").compute(bars)
        assert np.isfinite(frame["value"]).all() and len(frame) > 0
    # 停牌日没有成交均价，用到它的公式这一天没有值。
    day = pd.bdate_range("2025-01-02", periods=DAYS)[25]
    vwap_based = next(f for f in alpha101_factors() if f.name == "alpha101_041").compute(bars)
    assert vwap_based[(vwap_based["symbol"] == "S1") & (vwap_based["date"] == day)].empty


def test_a_vwap_outside_the_days_range_is_rejected_as_a_unit_mismatch():
    bars = make_bars()
    bars.loc[bars["symbol"].eq("S0"), "volume"] /= 100  # 成交量按“手”计：均价会放大 100 倍
    assert Panel(bars).vwap["S0"].isna().all() and Panel(bars).vwap["S1"].notna().all()
