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
    assert sorted({**REFERENCE, **REFERENCE_SECOND, **REFERENCE_THIRD}) == [item.number for item in FORMULAS]
    assert len(FORMULAS) == 100 == len({item.number for item in FORMULAS})
    assert 56 not in {item.number for item in FORMULAS}
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


@pytest.mark.parametrize("item", [item for item in FORMULAS if item.number in REFERENCE], ids=lambda item: f"alpha{item.number:03d}")
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

    for item in (item for item in FORMULAS if item.number in REFERENCE):
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
    for item in (item for item in FORMULAS if item.number in REFERENCE):
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


# --------------------------------------------------------------------------- #
# Second batch. The market is longer (the formulas reach back up to 250 days) and its prices
# are noisy around a slow drift, so cross-sectional ranks change every day.
# --------------------------------------------------------------------------- #


# 行业：S0-S4 同一大类（5 只，够在大类内比较）；S5、S6 另一大类（只有 2 只，和整个门类 C 比较）；
# S7-S9 在门类 J（只有 3 只，没有值）。
INDUSTRY = {0: "C13", 1: "C13", 2: "C13", 3: "C13", 4: "C13", 5: "C27", 6: "C27", 7: "J66", 8: "J66", 9: "J66"}


def make_lively_bars(days, stocks=10, seed=3):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=days)
    rows = []
    for s in range(stocks):
        close = 20 + 0.3 * np.cumsum(rng.normal(0, 0.15, days)) + rng.normal(0, 0.8, days)
        for t, day in enumerate(dates):
            spread = abs(rng.normal(0.3, 0.1)) + 0.05
            high, low = close[t] + spread, close[t] - spread
            open_ = low + rng.uniform(0.1, 0.9) * (high - low)
            volume = float(rng.integers(5_000, 90_000)) + rng.uniform(0, 1)
            vwap = low + rng.uniform(0.2, 0.8) * (high - low)
            rows.append({"symbol": f"S{s}", "trade_date": day, "raw_open": open_, "raw_high": high, "raw_low": low,
                         "raw_close": close[t], "volume": volume, "amount": vwap * volume, "adj_factor": 1.0, "adjusted_close": close[t],
                         "industry": INDUSTRY[s], "sector": INDUSTRY[s][0]})
    return pd.DataFrame(rows)


F = lambda d: int(math.floor(d))  # noqa: E731 - 论文：天数不是整数时向下取整


def r_window_f(x, d, fn):
    return r_window(x, F(d), fn)


def r_corr_f(x, y, d):
    return r_pair(x, y, F(d), _corr)


def r_decay(x, d):
    d = F(d)
    weights = np.arange(1, d + 1, dtype=float)      # 最早的一天权重 1，今天权重 d
    return r_window(x, d, lambda w: round(float(np.dot(w, weights) / weights.sum()), alpha101.MOMENT_DECIMALS))


def r_argmax(x, d):
    return r_window_f(x, d, lambda w: float(np.argmax(w) + 1))


def r_argmin(x, d):
    return r_window_f(x, d, lambda w: float(np.argmin(w) + 1))


def r_scale(x):
    out = np.full(x.shape, NAN)
    for t in range(x.shape[0]):
        total = np.nansum(np.abs(x[t]))
        if total > 0:
            out[t] = x[t] / total
    return out


def r_known(*parts):
    known = np.ones(np.shape(parts[0]), dtype=bool)
    for part in parts:
        known &= ~np.isnan(part)
    return known


def r_lt(a, b):
    b = np.broadcast_to(b, np.shape(a)).astype(float)
    return np.where(r_known(a, b), (a < b).astype(float), NAN)


def r_pick(condition, yes, no, *parts):
    """condition ? yes : no, missing unless every part is known."""
    shape = np.shape(parts[0])
    yes, no = np.broadcast_to(yes, shape), np.broadcast_to(no, shape)
    return np.where(r_known(*parts, yes, no), np.where(condition, yes, no), NAN)


def r_pow(x, a):
    a = np.broadcast_to(a, np.shape(x)).astype(float)
    return np.where(r_known(x, a), x ** a, NAN)


def r_spow(x, a):
    return np.sign(x) * r_pow(np.abs(x), a)


r_sum_f = lambda x, d: r_window_f(x, d, np.sum)  # noqa: E731
r_min_f = lambda x, d: r_window_f(x, d, np.min)  # noqa: E731
r_max_f = lambda x, d: r_window_f(x, d, np.max)  # noqa: E731
r_std_f = lambda x, d: r_window_f(x, d, lambda w: float(np.std(w, ddof=1)))  # noqa: E731
r_ts_rank_f = lambda x, d: r_ts_rank(x, F(d))  # noqa: E731
r_delta_f = lambda x, d: r_delta(x, F(d))  # noqa: E731
r_delay_f = lambda x, d: r_delay(x, F(d))  # noqa: E731
r_prod = lambda x, d: r_window_f(x, d, np.prod)  # noqa: E731
mix = lambda x, y, k: x * k + y * (1 - k)  # noqa: E731
inf_to_nan = lambda x: np.where(np.isinf(x), NAN, x)  # noqa: E731


class Market:
    """o, h, l, c, v: raw open/high/low/close/volume; amt: amount; w: vwap; r: returns; adv(d): average amount."""

    def __init__(self, bars):
        wide = lambda name: bars.pivot(index="trade_date", columns="symbol", values=name).to_numpy()  # noqa: E731
        self.o, self.h, self.l, self.c, self.v, self.amt = (wide(n) for n in ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "amount"))
        self.w = self.amt / self.v
        adjusted = wide("adjusted_close")
        self.r = np.full(self.c.shape, NAN)
        self.r[1:] = adjusted[1:] / adjusted[:-1] - 1
        self.hl2 = (self.h + self.l) / 2
        first = bars.drop_duplicates("symbol").set_index("symbol").sort_index()
        self.industry, self.sector = first["industry"].tolist(), first["sector"].tolist()

    def adv(self, d):
        return r_window(self.amt, d, np.mean)

    def neutral(self, x, level):
        """indneutralize: minus the day's mean of the stock's 大类 (at least 5 values that day), else of its 门类
        (at least 5), else missing. sector-level groups use the 门类 only."""
        out = np.full(x.shape, NAN)
        for t in range(x.shape[0]):
            valid = [j for j in range(x.shape[1]) if not math.isnan(x[t, j])]
            for s in valid:
                same_industry = [j for j in valid if self.industry[j] == self.industry[s]]
                same_sector = [j for j in valid if self.sector[j] == self.sector[s]]
                if level != "sector" and len(same_industry) >= 5:
                    out[t, s] = x[t, s] - np.mean(x[t, same_industry])
                elif len(same_sector) >= 5:
                    out[t, s] = x[t, s] - np.mean(x[t, same_sector])
        return out


def ref_slope(m):
    return ((r_delay(m.c, 20) - r_delay(m.c, 10)) / 10) - ((r_delay(m.c, 10) - m.c) / 10)


def ref021(m):
    mean8, std8, mean2, rel = r_sum(m.c, 8) / 8, r_std(m.c, 8), r_sum(m.c, 2) / 2, m.amt / m.adv(20)
    busy = r_pick((1 < rel) | (rel == 1), 1.0, -1.0, rel)
    lower = r_pick(mean2 < mean8 - std8, 1.0, busy, mean2, mean8, std8, busy)
    return r_pick(mean8 + std8 < mean2, -1.0, lower, mean8, std8, mean2, lower)


def ref046(m):
    x, fallback = ref_slope(m), -1 * (m.c - r_delay(m.c, 1))
    inner = r_pick(x < 0, 1.0, fallback, x, fallback)
    return r_pick(0.25 < x, -1.0, inner, x, fallback)


def ref_slope_rule(m, threshold):
    x, fallback = ref_slope(m), -1 * (m.c - r_delay(m.c, 1))
    return r_pick(x < -1 * threshold, 1.0, fallback, x, fallback)


def ref024(m):
    drift = r_delta(r_sum(m.c, 100) / 100, 100) / r_delay(m.c, 100)
    yes, no = -1 * (m.c - r_min(m.c, 100)), -1 * r_delta(m.c, 3)
    return r_pick((drift < 0.05) | (drift == 0.05), yes, no, drift, yes, no)


def ref001(m):
    spread = r_std(m.r, 20)
    base = r_pick(m.r < 0, spread, m.c, m.r, spread, m.c)
    return r_rank(r_argmax(r_spow(base, 2.0), 5)) - 0.5


def ref007(m):
    a20, move = m.adv(20), r_delta(m.c, 7)
    active = (-1 * r_ts_rank(np.abs(move), 60)) * np.sign(move)
    return r_pick(a20 < m.amt, active, -1.0, a20, m.amt, active)


def ref029(m):
    inner = r_sum(r_min(r_rank(r_rank(-1 * r_rank(r_delta(m.c - 1, 5)))), 2), 1)
    return r_min(r_prod(r_rank(r_rank(r_scale(np.log(inner)))), 1), 5) + r_ts_rank(r_delay(-1 * m.r, 6), 5)


# 编号 -> 论文原式，用上面的参考运算再写一遍（与 alpha101.py 分开写）。
REFERENCE_SECOND = {
    1: ref001,
    7: ref007,
    8: lambda m: -1 * r_rank((r_sum(m.o, 5) * r_sum(m.r, 5)) - r_delay(r_sum(m.o, 5) * r_sum(m.r, 5), 10)),
    17: lambda m: ((-1 * r_rank(r_ts_rank(m.c, 10))) * r_rank(r_delta(r_delta(m.c, 1), 1))) * r_rank(r_ts_rank(m.amt / m.adv(20), 5)),
    19: lambda m: (-1 * np.sign((m.c - r_delay(m.c, 7)) + r_delta(m.c, 7))) * (1 + r_rank(1 + r_sum(m.r, 250))),
    21: ref021,
    22: lambda m: -1 * (r_delta(r_corr(m.h, m.v, 5), 5) * r_rank(r_std(m.c, 20))),
    24: ref024,
    26: lambda m: -1 * r_max(r_corr(r_ts_rank(m.v, 5), r_ts_rank(m.h, 5), 5), 3),
    27: lambda m: (lambda level: r_pick(0.5 < level, -1.0, 1.0, level))(r_rank(r_sum(r_corr(r_rank(m.v), r_rank(m.w), 6), 2) / 2.0)),
    28: lambda m: r_scale((r_corr(m.adv(20), m.l, 5) + ((m.h + m.l) / 2)) - m.c),
    29: ref029,
    31: lambda m: ((r_rank(r_rank(r_rank(r_decay(-1 * r_rank(r_rank(r_delta(m.c, 10))), 10)))) + r_rank(-1 * r_delta(m.c, 3)))
                   + np.sign(r_scale(r_corr(m.adv(20), m.l, 12)))),
    32: lambda m: r_scale((r_sum(m.c, 7) / 7) - m.c) + (20 * r_scale(r_corr(m.w, r_delay(m.c, 5), 230))),
    35: lambda m: (r_ts_rank(m.v, 32) * (1 - r_ts_rank((m.c + m.h) - m.l, 16))) * (1 - r_ts_rank(m.r, 32)),
    36: lambda m: (((((2.21 * r_rank(r_corr(m.c - m.o, r_delay(m.v, 1), 15))) + (0.7 * r_rank(m.o - m.c)))
                     + (0.73 * r_rank(r_ts_rank(r_delay(-1 * m.r, 6), 5)))) + r_rank(np.abs(r_corr(m.w, m.adv(20), 6))))
                   + (0.6 * r_rank(((r_sum(m.c, 200) / 200) - m.o) * (m.c - m.o)))),
    37: lambda m: r_rank(r_corr(r_delay(m.o - m.c, 1), m.c, 200)) + r_rank(m.o - m.c),
    39: lambda m: (-1 * r_rank(r_delta(m.c, 7) * (1 - r_rank(r_decay(m.amt / m.adv(20), 9))))) * (1 + r_rank(r_sum(m.r, 250))),
    43: lambda m: r_ts_rank(m.amt / m.adv(20), 20) * r_ts_rank(-1 * r_delta(m.c, 7), 8),
    45: lambda m: -1 * ((r_rank(r_sum(r_delay(m.c, 5), 20) / 20) * r_corr(m.c, m.v, 2)) * r_rank(r_corr(r_sum(m.c, 5), r_sum(m.c, 20), 2))),
    46: ref046,
    47: lambda m: ((((r_rank(1 / m.c) * m.amt) / m.adv(20)) * ((m.h * r_rank(m.h - m.c)) / (r_sum(m.h, 5) / 5)))
                   - r_rank(m.w - r_delay(m.w, 5))),
    49: lambda m: ref_slope_rule(m, 0.1),
    50: lambda m: -1 * r_max(r_rank(r_corr(r_rank(m.v), r_rank(m.w), 5)), 5),
    51: lambda m: ref_slope_rule(m, 0.05),
    52: lambda m: (((-1 * r_min(m.l, 5)) + r_delay(r_min(m.l, 5), 5)) * r_rank((r_sum(m.r, 240) - r_sum(m.r, 20)) / 220)) * r_ts_rank(m.v, 5),
    55: lambda m: -1 * r_corr(r_rank(inf_to_nan((m.c - r_min(m.l, 12)) / (r_max(m.h, 12) - r_min(m.l, 12)))), r_rank(m.v), 6),
    57: lambda m: 0 - (1 * ((m.c - m.w) / r_decay(r_rank(r_argmax(m.c, 30)), 2))),
    60: lambda m: 0 - (1 * ((2 * r_scale(r_rank(inf_to_nan((((m.c - m.l) - (m.h - m.c)) / (m.h - m.l)) * m.v))))
                            - r_scale(r_rank(r_argmax(m.c, 10))))),
    61: lambda m: r_lt(r_rank(m.w - r_min_f(m.w, 16.1219)), r_rank(r_corr_f(m.w, m.adv(180), 17.9282))),
    62: lambda m: r_lt(r_rank(r_corr_f(m.w, r_sum_f(m.adv(20), 22.4101), 9.91009)),
                       r_rank(r_lt(r_rank(m.o) + r_rank(m.o), r_rank((m.h + m.l) / 2) + r_rank(m.h)))) * -1,
    64: lambda m: r_lt(r_rank(r_corr_f(r_sum_f(mix(m.o, m.l, 0.178404), 12.7054), r_sum_f(m.adv(120), 12.7054), 16.6208)),
                       r_rank(r_delta_f(mix(m.hl2, m.w, 0.178404), 3.69741))) * -1,
    65: lambda m: r_lt(r_rank(r_corr_f(mix(m.o, m.w, 0.00817205), r_sum_f(m.adv(60), 8.6911), 6.40374)),
                       r_rank(m.o - r_min_f(m.o, 13.635))) * -1,
    66: lambda m: (r_rank(r_decay(r_delta_f(m.w, 3.51013), 7.23052))
                   + r_ts_rank_f(r_decay(inf_to_nan((mix(m.l, m.l, 0.96633) - m.w) / (m.o - m.hl2)), 11.4157), 6.72611)) * -1,
    68: lambda m: r_lt(r_ts_rank_f(r_corr_f(r_rank(m.h), r_rank(m.adv(15)), 8.91644), 13.9333),
                       r_rank(r_delta_f(mix(m.c, m.l, 0.518371), 1.06157))) * -1,
    71: lambda m: np.maximum(
        r_ts_rank_f(r_decay(r_corr_f(r_ts_rank_f(m.c, 3.43976), r_ts_rank_f(m.adv(180), 12.0647), 18.0175), 4.20501), 15.6948),
        r_ts_rank_f(r_decay(r_pow(r_rank((m.l + m.o) - (m.w + m.w)), 2), 16.4662), 4.4388)),
    72: lambda m: (r_rank(r_decay(r_corr_f(m.hl2, m.adv(40), 8.93345), 10.1519))
                   / r_rank(r_decay(r_corr_f(r_ts_rank_f(m.w, 3.72469), r_ts_rank_f(m.v, 18.5188), 6.86671), 2.95011))),
    73: lambda m: np.maximum(
        r_rank(r_decay(r_delta_f(m.w, 4.72775), 2.91864)),
        r_ts_rank_f(r_decay((r_delta_f(mix(m.o, m.l, 0.147155), 2.03608) / mix(m.o, m.l, 0.147155)) * -1, 3.33829), 16.7411)) * -1,
    74: lambda m: r_lt(r_rank(r_corr_f(m.c, r_sum_f(m.adv(30), 37.4843), 15.1365)),
                       r_rank(r_corr_f(r_rank(mix(m.h, m.w, 0.0261661)), r_rank(m.v), 11.4791))) * -1,
    75: lambda m: r_lt(r_rank(r_corr_f(m.w, m.v, 4.24304)), r_rank(r_corr_f(r_rank(m.l), r_rank(m.adv(50)), 12.4413))),
    77: lambda m: np.minimum(r_rank(r_decay(((m.hl2 + m.h) - (m.w + m.h)), 20.0451)),
                             r_rank(r_decay(r_corr_f(m.hl2, m.adv(40), 3.1614), 5.64125))),
    78: lambda m: r_pow(r_rank(r_corr_f(r_sum_f(mix(m.l, m.w, 0.352233), 19.7428), r_sum_f(m.adv(40), 19.7428), 6.83313)),
                        r_rank(r_corr_f(r_rank(m.w), r_rank(m.v), 5.77492))),
    81: lambda m: r_lt(r_rank(np.log(r_prod(r_rank(r_pow(r_rank(r_corr_f(m.w, r_sum_f(m.adv(10), 49.6054), 8.47743)), 4)), 14.9655))),
                       r_rank(r_corr_f(r_rank(m.w), r_rank(m.v), 5.07914))) * -1,
    83: lambda m: ((r_rank(r_delay((m.h - m.l) / (r_sum(m.c, 5) / 5), 2)) * r_rank(r_rank(m.v)))
                   / (((m.h - m.l) / (r_sum(m.c, 5) / 5)) / (m.w - m.c))),
    84: lambda m: r_spow(r_ts_rank_f(m.w - r_max_f(m.w, 15.3217), 20.7127), r_delta_f(m.c, 4.96796)),
    85: lambda m: r_pow(r_rank(r_corr_f(mix(m.h, m.c, 0.876703), m.adv(30), 9.61331)),
                        r_rank(r_corr_f(r_ts_rank_f(m.hl2, 3.70596), r_ts_rank_f(m.v, 10.1595), 7.11408))),
    86: lambda m: r_lt(r_ts_rank_f(r_corr_f(m.c, r_sum_f(m.adv(20), 14.7444), 6.00049), 20.4195),
                       r_rank((m.o + m.c) - (m.w + m.o))) * -1,
    88: lambda m: np.minimum(
        r_rank(r_decay((r_rank(m.o) + r_rank(m.l)) - (r_rank(m.h) + r_rank(m.c)), 8.06882)),
        r_ts_rank_f(r_decay(r_corr_f(r_ts_rank_f(m.c, 8.44728), r_ts_rank_f(m.adv(60), 20.6966), 8.01266), 6.65053), 2.61957)),
    92: lambda m: np.minimum(
        r_ts_rank_f(r_decay(r_lt(m.hl2 + m.c, m.l + m.o), 14.7221), 18.8683),
        r_ts_rank_f(r_decay(r_corr_f(r_rank(m.l), r_rank(m.adv(30)), 7.58555), 6.94024), 6.80584)),
    94: lambda m: r_pow(r_rank(m.w - r_min_f(m.w, 11.5783)),
                        r_ts_rank_f(r_corr_f(r_ts_rank_f(m.w, 19.6462), r_ts_rank_f(m.adv(60), 4.02992), 18.0926), 2.70756)) * -1,
    95: lambda m: r_lt(r_rank(m.o - r_min_f(m.o, 12.4105)),
                       r_ts_rank_f(r_pow(r_rank(r_corr_f(r_sum_f(m.hl2, 19.1351), r_sum_f(m.adv(40), 19.1351), 12.8742)), 5), 11.7584)),
    96: lambda m: np.maximum(
        r_ts_rank_f(r_decay(r_corr_f(r_rank(m.w), r_rank(m.v), 3.83878), 4.16783), 8.38151),
        r_ts_rank_f(r_decay(r_argmax(r_corr_f(r_ts_rank_f(m.c, 7.45404), r_ts_rank_f(m.adv(60), 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1,
    98: lambda m: (r_rank(r_decay(r_corr_f(m.w, r_sum_f(m.adv(5), 26.4719), 4.58418), 7.18088))
                   - r_rank(r_decay(r_ts_rank_f(r_argmin(r_corr_f(r_rank(m.o), r_rank(m.adv(15)), 20.8187), 8.62571), 6.95668), 8.07206))),
    99: lambda m: r_lt(r_rank(r_corr_f(r_sum_f(m.hl2, 19.8975), r_sum_f(m.adv(60), 19.8975), 8.8136)),
                       r_rank(r_corr_f(m.l, m.v, 6.28259))) * -1,
}


def ref048(m):
    change = r_delta(m.c, 1)
    inner = (r_corr(change, r_delta(r_delay(m.c, 1), 1), 250) * change) / m.c
    return m.neutral(inner, "subindustry") / r_sum((r_delta(m.c, 1) / r_delay(m.c, 1)) ** 2, 250)


def ref100(m):
    pressure = m.neutral(m.neutral(r_rank(inf_to_nan((((m.c - m.l) - (m.h - m.c)) / (m.h - m.l)) * m.v)), "subindustry"), "subindustry")
    trend = m.neutral(r_corr(m.c, r_rank(m.adv(20)), 5) - r_rank(r_argmin(m.c, 30)), "subindustry")
    return 0 - (1 * (((1.5 * r_scale(pressure)) - r_scale(trend)) * (m.amt / m.adv(20))))


# 第三批：需要行业的 18 个公式（m.neutral 是论文的 indneutralize，按当天的值减去同组平均）。
REFERENCE_THIRD = {
    48: ref048,
    58: lambda m: -1 * r_ts_rank_f(r_decay(r_corr_f(m.neutral(m.w, "sector"), m.v, 3.92795), 7.89291), 5.50322),
    59: lambda m: -1 * r_ts_rank_f(r_decay(r_corr_f(m.neutral(mix(m.w, m.w, 0.728317), "industry"), m.v, 4.25197), 16.2289), 8.19648),
    63: lambda m: (r_rank(r_decay(r_delta_f(m.neutral(m.c, "industry"), 2.25164), 8.22237))
                   - r_rank(r_decay(r_corr_f(mix(m.w, m.o, 0.318108), r_sum_f(m.adv(180), 37.2467), 13.557), 12.2883))) * -1,
    67: lambda m: r_pow(r_rank(m.h - r_min_f(m.h, 2.14593)),
                        r_rank(r_corr_f(m.neutral(m.w, "sector"), m.neutral(m.adv(20), "subindustry"), 6.02936))) * -1,
    69: lambda m: r_pow(r_rank(r_max_f(r_delta_f(m.neutral(m.w, "industry"), 2.72412), 4.79344)),
                        r_ts_rank_f(r_corr_f(mix(m.c, m.w, 0.490655), m.adv(20), 4.92416), 9.0615)) * -1,
    70: lambda m: r_pow(r_rank(r_delta_f(m.w, 1.29456)), r_ts_rank_f(r_corr_f(m.neutral(m.c, "industry"), m.adv(50), 17.8256), 17.9171)) * -1,
    76: lambda m: np.maximum(
        r_rank(r_decay(r_delta_f(m.w, 1.24383), 11.8259)),
        r_ts_rank_f(r_decay(r_ts_rank_f(r_corr_f(m.neutral(m.l, "sector"), m.adv(81), 8.14941), 19.569), 17.1543), 19.383)) * -1,
    79: lambda m: r_lt(r_rank(r_delta_f(m.neutral(mix(m.c, m.o, 0.60733), "sector"), 1.23438)),
                       r_rank(r_corr_f(r_ts_rank_f(m.w, 3.60973), r_ts_rank_f(m.adv(150), 9.18637), 14.6644))),
    80: lambda m: r_pow(r_rank(np.sign(r_delta_f(m.neutral(mix(m.o, m.h, 0.868128), "industry"), 4.04545))),
                        r_ts_rank_f(r_corr_f(m.h, m.adv(10), 5.11456), 5.53756)) * -1,
    82: lambda m: np.minimum(
        r_rank(r_decay(r_delta_f(m.o, 1.46063), 14.8717)),
        r_ts_rank_f(r_decay(r_corr_f(m.neutral(m.v, "sector"), mix(m.o, m.o, 0.634196), 17.4842), 6.92131), 13.4283)) * -1,
    87: lambda m: np.maximum(
        r_rank(r_decay(r_delta_f(mix(m.c, m.w, 0.369701), 1.91233), 2.65461)),
        r_ts_rank_f(r_decay(np.abs(r_corr_f(m.neutral(m.adv(81), "industry"), m.c, 13.4132)), 4.89768), 14.4535)) * -1,
    89: lambda m: (r_ts_rank_f(r_decay(r_corr_f(mix(m.l, m.l, 0.967285), m.adv(10), 6.94279), 5.51607), 3.79744)
                   - r_ts_rank_f(r_decay(r_delta_f(m.neutral(m.w, "industry"), 3.48158), 10.1466), 15.3012)),
    90: lambda m: r_pow(r_rank(m.c - r_max_f(m.c, 4.66719)),
                        r_ts_rank_f(r_corr_f(m.neutral(m.adv(40), "subindustry"), m.l, 5.38375), 3.21856)) * -1,
    91: lambda m: (r_ts_rank_f(r_decay(r_decay(r_corr_f(m.neutral(m.c, "industry"), m.v, 9.74928), 16.398), 3.83219), 4.8667)
                   - r_rank(r_decay(r_corr_f(m.w, m.adv(30), 4.01303), 2.6809))) * -1,
    93: lambda m: (r_ts_rank_f(r_decay(r_corr_f(m.neutral(m.w, "industry"), m.adv(81), 17.4193), 19.848), 7.54455)
                   / r_rank(r_decay(r_delta_f(mix(m.c, m.w, 0.524434), 2.77377), 16.2664))),
    97: lambda m: (r_rank(r_decay(r_delta_f(m.neutral(mix(m.l, m.w, 0.721001), "industry"), 3.3705), 20.4523))
                   - r_ts_rank_f(r_decay(r_ts_rank_f(r_corr_f(r_ts_rank_f(m.l, 7.87871), r_ts_rank_f(m.adv(60), 17.255), 4.97547), 18.5925),
                                         15.7152), 6.71659)) * -1,
    100: ref100,
}
LIVELY = {**REFERENCE_SECOND, **REFERENCE_THIRD}

# 在随机行情上几乎没有值的公式：内层是很短的相关系数，一边常常几天不变（相关系数没有定义）。
SPARSE = {96, 97}
# 第一天有没有值取决于行情：10 只股票的 rank(adv20) 常常 5 天不变，内层的相关系数没有定义。
LATE_START = {100}


def lively_days(item):
    return item.history + 40


@pytest.mark.parametrize("number", sorted(LIVELY))
def test_second_and_third_batch_match_the_day_by_day_reference(number):
    item = next(item for item in FORMULAS if item.number == number)
    bars = make_lively_bars(lively_days(item))
    expected = LIVELY[number](Market(bars))
    expected = np.where(np.isinf(expected), NAN, expected)
    actual = computed(bars, number)
    if number not in SPARSE:
        assert np.isfinite(actual).sum() > 40, "the formula should produce values on this market"
        first = next(t for t in range(len(actual)) if np.isfinite(actual[t]).any())
        if number in LATE_START:
            assert first >= item.history - 1
        else:
            assert first == item.history - 1, f"first value on day {first + 1}, declared {item.history}"
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-9, equal_nan=True)


@pytest.mark.parametrize("item", FORMULAS, ids=lambda item: f"alpha{item.number:03d}")
def test_after_an_ex_date_the_values_match_a_market_already_on_the_new_basis(item):
    # 第 3 只股票从 ex 天起价格减半、成交量加倍（10 送 10）。窗口完全落在除权之后的值，必须和
    # 整段历史都已经在新基准上的市场完全一样：这说明 span 覆盖了公式用到的全部原始价量。
    days = max(DAYS, item.history + item.span + 30)
    dates = pd.bdate_range("2024-01-02", periods=days)
    plain = make_lively_bars(days, stocks=7)
    ex = item.history + 5
    split, rebased = plain.copy(), plain.copy()
    after = split["symbol"].eq("S3") & (split["trade_date"] >= dates[ex])
    for frame, mask in ((split, after), (rebased, rebased["symbol"].eq("S3"))):
        frame.loc[mask, ["raw_open", "raw_high", "raw_low", "raw_close"]] /= 2
        frame.loc[mask, "volume"] *= 2
    split.loc[split["symbol"].eq("S3") & ~after, "adj_factor"] = 0.5
    split["adjusted_close"] = split["raw_close"] * split["adj_factor"]
    rebased["adjusted_close"] = rebased["raw_close"]
    values, reference = computed(split, item.number), computed(rebased, item.number)
    assert np.isnan(values[ex:ex + item.span, 3]).all()
    np.testing.assert_allclose(values[ex + item.span:], reference[ex + item.span:], rtol=1e-7, atol=1e-10, equal_nan=True)
    # 除权之前的值和从来没有除权的市场一样：没有用到以后的除权。
    np.testing.assert_allclose(values[:ex], computed(plain, item.number)[:ex], rtol=1e-9, atol=1e-12, equal_nan=True)
    if item.span == 0 and item.history < ex:
        assert np.isfinite(values[ex - 5:ex + 5, 3]).all(), "按当天前复权价计算的公式，跨过除权日也有值"


def test_a_peers_split_or_return_from_suspension_does_not_move_the_industry_mean():
    # 六只股票同一大类，价格都不变。S1 从第 4 天起 10 送 10（价格减半、成交量加倍），S2 第 3 天停牌。
    days = pd.bdate_range("2025-01-02", periods=6)
    rows = []
    for s in range(6):
        for t, day in enumerate(days):
            if s == 2 and t == 2:
                continue
            split = s == 1 and t >= 3
            price, volume = (10.0 + s) / (2 if split else 1), 100.0 * (2 if split else 1)
            factor = 1.0 if split or s != 1 else 0.5
            rows.append({"symbol": f"S{s}", "trade_date": day, "raw_open": price, "raw_high": price, "raw_low": price, "raw_close": price,
                         "volume": volume, "amount": price * volume, "adj_factor": factor, "adjusted_close": price * factor,
                         "industry": "C13", "sector": "C"})
    p = Panel(pd.DataFrame(rows))
    same_day, series = p.neutralize(p.close, "industry"), p.neutralize_series(p.close, "price", "industry")
    assert same_day["S0"].diff().abs().max() > 0.5                        # 当天的平均值跟着停牌、送转跳动
    assert series["S0"].diff().dropna().abs().max() < 1e-12                 # 组平均只随真实的价格变化移动
    assert series.iloc[0].tolist() == pytest.approx(same_day.iloc[0].tolist())
    # 停牌那天没有值；复牌后从当天的组平均重新算起。
    assert np.isnan(series.loc[days[2], "S2"]) and series.loc[days[3], "S2"] == pytest.approx(same_day.loc[days[3], "S2"])
    volume = p.neutralize_series(p.volume, "volume", "industry")
    assert volume["S0"].diff().dropna().abs().max() < 1e-12


def test_small_industries_are_compared_with_their_sector_and_an_unknown_industry_has_no_value():
    bars = make_lively_bars(5)
    p = Panel(bars)
    value = p.neutralize(p.close, "industry")
    close = p.close
    assert value["S0"].tolist() == pytest.approx((close["S0"] - close[["S0", "S1", "S2", "S3", "S4"]].mean(axis=1)).tolist())
    assert value["S5"].tolist() == pytest.approx((close["S5"] - close[[f"S{i}" for i in range(7)]].mean(axis=1)).tolist())
    assert value[["S7", "S8", "S9"]].isna().all().all()                     # 门类 J 只有 3 只
    sector = p.neutralize(p.close, "sector")
    assert sector["S0"].tolist() == pytest.approx((close["S0"] - close[[f"S{i}" for i in range(7)]].mean(axis=1)).tolist())
    with pytest.raises(ValueError, match="行业分类"):
        unclassified = Panel(bars.drop(columns=["industry", "sector"]))
        unclassified.neutralize(unclassified.close, "industry")


def test_new_operators_by_hand():
    x = pd.DataFrame({"a": [1.0, 3.0, 2.0, 5.0], "b": [4.0, 4.0, 1.0, np.nan]})
    # decay_linear(x, 3)：今天权重 3、昨天 2、前天 1。
    assert alpha101.decay_linear(x, 3.9)["a"].tolist()[2:] == pytest.approx([(1 * 1 + 3 * 2 + 2 * 3) / 6, (3 * 1 + 2 * 2 + 5 * 3) / 6])
    assert np.isnan(alpha101.decay_linear(x, 3)["b"].iloc[3])
    # 窗口里最大值在第几天：最早的一天是 1；并列时取最早的那天。
    assert alpha101.ts_argmax(x, 3)["a"].tolist()[2:] == [2.0, 3.0]
    assert alpha101.ts_argmax(x, 2)["b"].tolist()[1:3] == [1.0, 1.0]
    assert alpha101.ts_argmin(x, 3)["a"].tolist()[2:] == [1.0, 2.0]
    assert alpha101.product(x, 2)["a"].tolist()[1:] == [3.0, 6.0, 10.0]
    assert alpha101.scale(x)["a"].tolist() == pytest.approx([0.2, 3 / 7, 2 / 3, 1.0])
    # 两天的相关系数只看变化方向；有一边不变时没有定义。
    pair = alpha101.correlation(pd.DataFrame({"s": [1.0, 2.0, 1.0, 1.0]}), pd.DataFrame({"s": [5.0, 7.0, 9.0, 8.0]}), 2)["s"]
    assert pair.tolist()[1:3] == [1.0, -1.0] and np.isnan(pair.iloc[3])
    # 1 的任何次方是 1，但指数缺失时结果也缺失。
    assert np.isnan(alpha101.power(pd.DataFrame({"s": [1.0]}), pd.DataFrame({"s": [np.nan]}))["s"].iloc[0])
    assert alpha101.signed_power(pd.DataFrame({"s": [-2.0, 3.0]}), 2.0)["s"].tolist() == [-4.0, 9.0]
    # 条件表达式：每一部分都能算出来才有值，哪怕没被选中的那一边。
    a, b = x[["a"]], x[["b"]].set_axis(["a"], axis=1)          # 同一列名：同一只股票的两个值
    chosen = alpha101.choose(a > 2, a, b, a, b)
    assert chosen["a"].tolist()[:3] == [4.0, 3.0, 1.0] and np.isnan(chosen["a"].iloc[3])
    assert alpha101.less(x[["a"]], 2.5)["a"].tolist() == [1.0, 0.0, 1.0, 0.0]


@pytest.mark.parametrize("item", FORMULAS, ids=lambda item: f"alpha{item.number:03d}")
def test_each_formula_needs_only_the_columns_it_declares(item):
    # 回测时策略只取因子声明的列（可选列有就带上）：少声明一列，回测里就算不出来。
    bars = make_lively_bars(lively_days(item))
    factor = next(f for f in alpha101_factors() if f.name == f"alpha101_{item.number:03d}")
    columns = ["symbol", "trade_date", *factor.required_fields, *(c for c in factor.optional_fields if c in bars.columns)]
    narrow = factor.compute(bars[list(dict.fromkeys(columns))])
    full = factor.compute(bars)
    pd.testing.assert_frame_equal(narrow, full)
