"""The 101 Formulaic Alphas computed from daily bars, all but #56 (market cap).

Source: https://arxiv.org/abs/1601.00991 (Appendix A). Each formula below is the paper's,
with the paper's operator definitions. 82 of the 101 need only daily price and volume, 18 more
need an industry classification, and #56 needs market cap (not here yet).

Conventions, chosen so that no value depends on data after its own date:

- Prices and volume are the raw ones of each day. No adjusted price stands in for them, so
  price levels and same-day comparisons are the ones traders saw.
- ``returns`` is the true close-to-close return (from the adjusted close), so an ex-dividend
  day is not counted as a loss.
- ``vwap`` is amount / volume of the day; ``adv{d}`` is the average amount over ``d`` days,
  as the paper defines it.
- A dividend or split makes raw prices and volumes before and after it incomparable. A value
  whose price/volume window spans such a day is left missing rather than computed from a
  jump that never traded (``span`` below is the number of day-to-day steps the window covers).
  Other stocks' cross-sectional ranks on that day still count the affected stock.
- Windows longer than 200 days (24, 32, 36, 37, 48) would cross the yearly dividend of almost
  every stock, so these use each day's forward-adjusted prices instead: on day t every price in
  the window is put on day t's basis (``Panel.adjusted`` / ``Panel.on_today``). The ratio of two
  factors depends only on the actions between their days, so nothing later is used.
- ``indneutralize(x, IndClass.level)`` subtracts the day's group mean. Groups are the CSRC
  classification in force that day: ``sector`` is the 门类 (19), ``industry`` the 大类;
  there is no finer level, so ``subindustry`` is the 大类 too (the paper allows different
  classifications per level). When fewer than ``MIN_GROUP`` stocks of a 大类 have a value that
  day, the stock is compared with its whole 门类; when the 门类 has fewer too, it has no value.
  A neutralized series that a time-series operator reads (delta, correlation) keeps the group
  mean from jumping when a peer pays a dividend, splits, resumes trading or changes group
  (``Panel.neutralize_series``).
- ``rank`` is the cross-sectional average percentile rank within the supplied universe; when
  the bars carry an ``in_universe`` mark (an index's members on each day), only that day's
  members are ranked (``scale`` too);
- A non-integer number of days is floored, as the paper says. ``ts_argmax``/``ts_argmin`` say
  which day of the window holds the extreme, 1 for the oldest and d for today (the paper does
  not say which end to count from). ``max``/``min`` of two expressions are taken element-wise;
  with a number of days as the second argument they are ``ts_max``/``ts_min``, as defined.
- A ``condition ? yes : no`` has a value only once every part of it can be computed.
- The formulas that compare ``volume`` with ``adv`` (7, 17, 21, 39, 43, 47) use the day's amount
  in place of ``volume``: ``adv`` is an average amount, so the paper's comparison mixes shares
  with money and would rank stocks by their price level instead of their activity.
  ``ts_rank`` the same within a stock's own window. Undefined results stay missing.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_platform.data.index_constituents import UNIVERSE_COLUMN
from quant_platform.data.industry import MISSING_INDUSTRY_MESSAGE
from quant_platform.factors.base import FactorDefinition, melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor

# 复权因子相邻两天的变化超过这个比例，就认为这一天发生了除权除息。
ACTION_THRESHOLD = 1e-3
# 行业内比较至少要有这么多只股票；不够时和整个门类比较。
MIN_GROUP = 5

Frame = pd.DataFrame


# --------------------------------------------------------------------------- #
# Operators (paper, Appendix A.1). Frames are date x symbol.
# --------------------------------------------------------------------------- #


# 研究范围是指数当时的成分股时，截面排名只在当天的成分股之间进行（日期 x 股票的布尔表）。
_UNIVERSE: ContextVar[Frame | None] = ContextVar("alpha101_universe", default=None)


def _days(d: float) -> int:
    """The paper: a non-integer number of days d is converted to floor(d)."""

    return int(math.floor(d))


def _cross_section(x: Frame) -> Frame:
    """The values that take part in a cross-sectional operation: that day's members only, when a universe is set."""

    members = _UNIVERSE.get()
    if members is None:
        return x
    return x.where(members.reindex(index=x.index, columns=x.columns, fill_value=False))


def rank(x: Frame) -> Frame:
    return _cross_section(x).rank(axis=1, pct=True)


def scale(x: Frame, a: float = 1.0) -> Frame:
    """Rescaled across stocks so that the absolute values of each day sum to ``a``."""

    x = _cross_section(x)
    return x.div(x.abs().sum(axis=1).replace(0, np.nan), axis=0) * a


def delay(x: Frame, d: float) -> Frame:
    return x.shift(_days(d))


def delta(x: Frame, d: float) -> Frame:
    return x.diff(_days(d))


def ts_sum(x: Frame, d: float) -> Frame:
    return x.rolling(_days(d), min_periods=_days(d)).sum()


def ts_min(x: Frame, d: float) -> Frame:
    return x.rolling(_days(d), min_periods=_days(d)).min()


def ts_max(x: Frame, d: float) -> Frame:
    return x.rolling(_days(d), min_periods=_days(d)).max()


def ts_rank(x: Frame, d: float) -> Frame:
    return x.rolling(_days(d), min_periods=_days(d)).rank(pct=True)


def stddev(x: Frame, d: float) -> Frame:
    return x.rolling(_days(d), min_periods=_days(d)).std()


def decay_linear(x: Frame, d: float) -> Frame:
    """Weighted average of the past d days with weights d (today), d - 1, ..., 1, rescaled to sum to 1."""

    d = _days(d)
    total = sum(x.shift(k) * (d - k) for k in range(d))
    # 输入常常是排名：两只股票的加权平均精确相等时，舍入误差不应该在之后的排名里分出先后。
    return (total / (d * (d + 1) / 2)).round(MOMENT_DECIMALS)


def _over_window(x: Frame, d: float, reduce: Callable[[np.ndarray], np.ndarray]) -> Frame:
    """``reduce`` applied to each stock's last d values; missing when any of them is."""

    d = _days(d)
    values = x.to_numpy(dtype=float)
    out = np.full(values.shape, np.nan)
    if len(values) >= d:
        windows = np.lib.stride_tricks.sliding_window_view(values, d, axis=0)
        result = reduce(np.nan_to_num(windows, nan=0.0)).astype(float)
        result[np.isnan(windows).any(axis=-1)] = np.nan
        out[d - 1:] = result
    return pd.DataFrame(out, index=x.index, columns=x.columns)


def ts_argmax(x: Frame, d: float) -> Frame:
    """Which day of the window the maximum fell on: 1 for the oldest day, d for today (the earliest one on ties)."""

    return _over_window(x, d, lambda windows: np.argmax(windows, axis=-1) + 1)


def ts_argmin(x: Frame, d: float) -> Frame:
    """Which day of the window the minimum fell on, counted the same way as ``ts_argmax``."""

    return _over_window(x, d, lambda windows: np.argmin(windows, axis=-1) + 1)


def product(x: Frame, d: float) -> Frame:
    return _over_window(x, d, lambda windows: np.prod(windows, axis=-1))


def power(x: Frame, a: Frame | float) -> Frame:
    """x^a, missing when either side is (numpy would make 1 ** missing equal to 1)."""

    result = x ** a
    return result.where(_known(x, a)) if isinstance(a, pd.DataFrame) else result


def signed_power(x: Frame, a: Frame | float) -> Frame:
    return np.sign(x) * power(x.abs(), a)


def elementwise_max(x: Frame, y: Frame) -> Frame:
    """``max(x, y)`` of two expressions (the paper's max(x, d) is ts_max when d is a number of days)."""

    return np.maximum(x, y)


def elementwise_min(x: Frame, y: Frame) -> Frame:
    return np.minimum(x, y)


def _known(*parts: Frame) -> Frame:
    known = None
    for part in parts:
        known = part.notna() if known is None else known & part.notna()
    return known


def less(x: Frame, y: Frame | float) -> Frame:
    """1 where x < y, 0 where not, missing where either side is."""

    y_frame = y if isinstance(y, pd.DataFrame) else pd.DataFrame(y, index=x.index, columns=x.columns)
    return (x < y_frame).astype(float).where(_known(x, y_frame))


def choose(condition: Frame, yes: Frame | float, no: Frame | float, *parts: Frame) -> Frame:
    """``condition ? yes : no``. A value exists only when every part of the expression can be computed,
    so that the first value never depends on which branch a stock happened to take."""

    frames = [part for part in (*parts, yes, no) if isinstance(part, pd.DataFrame)]
    shape = frames[0]
    pick = lambda value: value if isinstance(value, pd.DataFrame) else pd.DataFrame(value, index=shape.index, columns=shape.columns)  # noqa: E731
    result = pick(yes).where(condition.astype(bool), pick(no))
    return result.where(_known(*frames))


# 相关系数和协方差保留的小数位。滚动计算会留下 1e-16 量级的舍入误差；不去掉的话，
# 数学上相等的两个值会在之后的 rank 里被排出先后。
MOMENT_DECIMALS = 12


def _flat(x: Frame, d: int) -> Frame:
    """Windows in which the series did not move: their covariance is exactly zero and their
    correlation undefined, whatever rounding noise the rolling computation leaves."""

    return ts_max(x, d) == ts_min(x, d)


def correlation(x: Frame, y: Frame, d: float) -> Frame:
    d = _days(d)
    if d == 2:
        # 两天的相关系数只能是 1 或 -1：直接按两天的变化方向算。滚动计算会留下 1e-9 量级的误差，
        # 让本该并列的排名分出先后。
        step = x.diff() * y.diff()
        return np.sign(step).where(step != 0)
    result = x.rolling(d, min_periods=d).corr(y).replace([np.inf, -np.inf], np.nan)
    return result.where(~(_flat(x, d) | _flat(y, d))).round(MOMENT_DECIMALS)


def covariance(x: Frame, y: Frame, d: float) -> Frame:
    d = _days(d)
    result = x.rolling(d, min_periods=d).cov(y)
    return result.where(~(_flat(x, d) | _flat(y, d)) | result.isna(), 0.0).round(MOMENT_DECIMALS)


def _group_stats(values: np.ndarray, codes: np.ndarray, groups: int) -> tuple[np.ndarray, np.ndarray]:
    """For each cell [day, stock]: the mean of its group's values that day and how many there are.

    ``codes`` gives each cell's group (``-1``: none); only cells with a value count."""

    days, width = values.shape[0], max(groups, 1)
    key = np.arange(days)[:, None] * width + np.where(codes >= 0, codes, 0)
    counted = ~np.isnan(values) & (codes >= 0)
    sums = np.bincount(key[counted], weights=values[counted], minlength=days * width)
    counts = np.bincount(key[counted], minlength=days * width)
    known = codes >= 0
    mean = np.where(known, sums[key] / np.maximum(counts[key], 1), np.nan)
    return mean, np.where(known, counts[key], 0)


# --------------------------------------------------------------------------- #
# Inputs (paper, Appendix A.2)
# --------------------------------------------------------------------------- #


class Panel:
    """The wide frames the formulas share, built once per computation."""

    def __init__(self, bars: pd.DataFrame) -> None:
        self._bars = bars
        self._cache: dict[str, Frame] = {}

    def _field(self, name: str) -> Frame:
        if name not in self._cache:
            self._cache[name] = pivot_field(self._bars, name)
        return self._cache[name]

    @property
    def open(self) -> Frame:
        return self._field("raw_open")

    @property
    def high(self) -> Frame:
        return self._field("raw_high")

    @property
    def low(self) -> Frame:
        return self._field("raw_low")

    @property
    def close(self) -> Frame:
        return self._field("raw_close")

    @property
    def volume(self) -> Frame:
        # 停牌日成交量为 0，不是一个可以比较的成交量。
        volume = self._field("volume")
        return volume.where(volume > 0)

    @property
    def amount(self) -> Frame:
        amount = self._field("amount")
        return amount.where(amount > 0)

    @property
    def vwap(self) -> Frame:
        if "vwap" not in self._cache:
            vwap = self.amount / self.volume
            # 成交均价一定落在当天的最低价和最高价之间；落在外面说明成交量或成交额的单位不对。
            inside = (vwap >= self.low * 0.999) & (vwap <= self.high * 1.001)
            self._cache["vwap"] = vwap.where(inside)
        return self._cache["vwap"]

    @property
    def returns(self) -> Frame:
        if "returns" not in self._cache:
            raw = self.close.pct_change(fill_method=None)
            if "adjusted_close" in self._bars.columns:
                true = self._field("adjusted_close").pct_change(fill_method=None)
                raw = true.where(true.notna(), raw)
            self._cache["returns"] = raw.replace([np.inf, -np.inf], np.nan)
        return self._cache["returns"]

    def adv(self, d: int) -> Frame:
        return self.amount.rolling(d, min_periods=d).mean()

    @property
    def _action(self) -> Frame | None:
        """True on days whose prices are not comparable with the day before (dividend, split)."""

        if "action" not in self._cache:
            if "adj_factor" not in self._bars.columns:
                return None
            factor = self._field("adj_factor")
            self._cache["action"] = ((factor / factor.shift(1) - 1.0).abs() > ACTION_THRESHOLD).astype(float)
        return self._cache["action"]

    def comparable(self, values: Frame, span: int) -> Frame:
        """Blank the values whose window of ``span`` day-to-day steps crosses a corporate action."""

        action = self._action
        if span <= 0 or action is None:
            return values
        crossed = action.rolling(span, min_periods=1).max() > 0
        return values.where(~crossed.reindex(index=values.index, columns=values.columns, fill_value=False))

    # ----------------------------------------------------------------------- #
    # Each day's forward-adjusted prices (the long-window formulas)
    # ----------------------------------------------------------------------- #

    def _factor(self, like: Frame) -> Frame:
        """The adjustment factor of each day, shaped like ``like``; 1 when the bars carry none."""

        if "adj_factor" not in self._bars.columns:
            return pd.DataFrame(1.0, index=like.index, columns=like.columns)
        factor = self._field("adj_factor")
        return factor.where(factor > 0).reindex(index=like.index, columns=like.columns)

    def adjusted(self, x: Frame, kind: str = "price") -> Frame:
        """``x`` on one basis across dividends and splits: prices times the factor, volumes divided by it.

        Within a window these differ from the window's last-day forward-adjusted values only by one
        constant, so ratios, correlations and ranks are the ones on that day's basis."""

        return x * self._factor(x) if kind == "price" else x / self._factor(x)

    def on_today(self, x: Frame) -> Frame:
        """A price amount on the ``adjusted`` basis, expressed on each day's own basis."""

        return x / self._factor(x)

    # ----------------------------------------------------------------------- #
    # indneutralize
    # ----------------------------------------------------------------------- #

    def _codes(self, column: str, like: Frame) -> tuple[np.ndarray, int]:
        """Integer group codes (``-1`` where unknown) for each cell of ``like``."""

        key = f"codes:{column}"
        if key not in self._cache:
            if column not in self._bars.columns or not self._bars[column].notna().any():
                raise ValueError(MISSING_INDUSTRY_MESSAGE)
            frame = self._bars[["trade_date", "symbol", column]].copy()
            frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.normalize()
            frame[column] = frame[column].astype(object).where(frame[column].notna(), None)
            self._cache[key] = frame.groupby(["trade_date", "symbol"])[column].last().unstack("symbol").sort_index()
        labels = self._cache[key].reindex(index=like.index, columns=like.columns)
        codes, uniques = pd.factorize(labels.to_numpy(dtype=object).ravel())
        return codes.reshape(labels.shape), len(uniques)

    def _peer_mean(self, values: Frame, level: str) -> np.ndarray:
        """Each cell's group mean on its day: the stock's 大类 when at least ``MIN_GROUP`` of its stocks
        have a value that day, otherwise its 门类 when that has, otherwise missing."""

        x = values.to_numpy(dtype=float)
        sector_mean, sector_count = _group_stats(x, *self._codes("sector", values))
        sector_mean = np.where(sector_count >= MIN_GROUP, sector_mean, np.nan)
        if level == "sector":
            return sector_mean
        industry_mean, industry_count = _group_stats(x, *self._codes("industry", values))
        return np.where(industry_count >= MIN_GROUP, industry_mean, sector_mean)

    def neutralize(self, x: Frame, level: str) -> Frame:
        """The paper's indneutralize: ``x`` minus its group's mean that day (``level``: sector, industry, subindustry)."""

        x = _cross_section(x)
        return x - self._peer_mean(x, level)

    def neutralize_series(self, x: Frame, kind: str, level: str) -> Frame:
        """indneutralize for a series a time-series operator then reads (delta, correlation).

        On the first day of each run of values a stock has, it is ``x`` minus its group mean, as
        defined. After that the stock's group mean moves by the mean of the members' changes from
        the day before, each change measured on that day's basis (``kind``: price, volume or
        amount). So a peer's dividend or split, a peer resuming from a suspension, or a stock
        joining or leaving the group does not make the mean jump. The operators that read the
        series only use differences within a window, and those are the paper's whenever no such
        event happens.
        """

        x = _cross_section(x)
        before, factor = x.shift(1), self._factor(x)
        if kind == "price":
            before = before * factor.shift(1) / factor
        elif kind == "volume":
            before = before * factor / factor.shift(1)
        step = self._peer_mean(x - before, level)
        start = (x.notna() & x.shift(1).isna()).to_numpy()
        moves = np.where(start, self._peer_mean(x, level), step)
        total = np.nancumsum(moves, axis=0)
        # 每段从开头那天的组平均算起：减去这一段开始之前累计的变化。
        offset = pd.DataFrame(np.where(start, total - np.nan_to_num(moves), np.nan), index=x.index, columns=x.columns).ffill()
        return (x - (total - offset.to_numpy())).where(np.isfinite(moves))


# --------------------------------------------------------------------------- #
# Formulas. The comment above each function is the paper's expression.
# --------------------------------------------------------------------------- #


# (-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))
def _alpha002(p: Panel) -> Frame:
    return -correlation(rank(delta(np.log(p.volume), 2)), rank((p.close - p.open) / p.open), 6)


# (-1 * correlation(rank(open), rank(volume), 10))
def _alpha003(p: Panel) -> Frame:
    return -correlation(rank(p.open), rank(p.volume), 10)


# (-1 * Ts_Rank(rank(low), 9))
def _alpha004(p: Panel) -> Frame:
    return -ts_rank(rank(p.low), 9)


# (rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))
def _alpha005(p: Panel) -> Frame:
    return rank(p.open - ts_sum(p.vwap, 10) / 10) * (-rank(p.close - p.vwap).abs())


# (-1 * correlation(open, volume, 10))
def _alpha006(p: Panel) -> Frame:
    return -correlation(p.open, p.volume, 10)


def _trend_confirmed_change(p: Panel, d: int) -> Frame:
    """delta(close, 1) while the last ``d`` changes all share one sign, its negative otherwise."""

    change = delta(p.close, 1)
    lowest, highest = ts_min(change, d), ts_max(change, d)
    return change.where((lowest > 0) | (highest < 0), -change).where(lowest.notna())


# ((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1)
#   : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))
def _alpha009(p: Panel) -> Frame:
    return _trend_confirmed_change(p, 5)


# rank(((0 < ts_min(delta(close, 1), 4)) ? delta(close, 1)
#   : ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))))
def _alpha010(p: Panel) -> Frame:
    return rank(_trend_confirmed_change(p, 4))


# ((rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) * rank(delta(volume, 3)))
def _alpha011(p: Panel) -> Frame:
    gap = p.vwap - p.close
    return (rank(ts_max(gap, 3)) + rank(ts_min(gap, 3))) * rank(delta(p.volume, 3))


# (sign(delta(volume, 1)) * (-1 * delta(close, 1)))
def _alpha012(p: Panel) -> Frame:
    return np.sign(delta(p.volume, 1)) * -delta(p.close, 1)


# (-1 * rank(covariance(rank(close), rank(volume), 5)))
def _alpha013(p: Panel) -> Frame:
    return -rank(covariance(rank(p.close), rank(p.volume), 5))


# ((-1 * rank(delta(returns, 3))) * correlation(open, volume, 10))
def _alpha014(p: Panel) -> Frame:
    return -rank(delta(p.returns, 3)) * correlation(p.open, p.volume, 10)


# (-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))
def _alpha015(p: Panel) -> Frame:
    return -ts_sum(rank(correlation(rank(p.high), rank(p.volume), 3)), 3)


# (-1 * rank(covariance(rank(high), rank(volume), 5)))
def _alpha016(p: Panel) -> Frame:
    return -rank(covariance(rank(p.high), rank(p.volume), 5))


# (-1 * rank(((stddev(abs((close - open)), 5) + (close - open)) + correlation(close, open, 10))))
def _alpha018(p: Panel) -> Frame:
    body = p.close - p.open
    return -rank(stddev(body.abs(), 5) + body + correlation(p.close, p.open, 10))


# (((-1 * rank((open - delay(high, 1)))) * rank((open - delay(close, 1)))) * rank((open - delay(low, 1))))
def _alpha020(p: Panel) -> Frame:
    return -rank(p.open - delay(p.high, 1)) * rank(p.open - delay(p.close, 1)) * rank(p.open - delay(p.low, 1))


# (((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)
def _alpha023(p: Panel) -> Frame:
    average = ts_sum(p.high, 20) / 20
    return (-delta(p.high, 2)).where(average < p.high, 0.0).where(average.notna() & p.high.notna())


# rank(((((-1 * returns) * adv20) * vwap) * (high - close)))
def _alpha025(p: Panel) -> Frame:
    return rank(-p.returns * p.adv(20) * p.vwap * (p.high - p.close))


# (((1.0 - rank(((sign((close - delay(close, 1))) + sign((delay(close, 1) - delay(close, 2))))
#   + sign((delay(close, 2) - delay(close, 3)))))) * sum(volume, 5)) / sum(volume, 20))
def _alpha030(p: Panel) -> Frame:
    change = np.sign(delta(p.close, 1))
    streak = change + delay(change, 1) + delay(change, 2)
    return (1.0 - rank(streak)) * ts_sum(p.volume, 5) / ts_sum(p.volume, 20)


# rank((-1 * ((1 - (open / close))^1)))
def _alpha033(p: Panel) -> Frame:
    return rank(p.open / p.close.replace(0, np.nan) - 1)


# rank(((1 - rank((stddev(returns, 2) / stddev(returns, 5)))) + (1 - rank(delta(close, 1)))))
def _alpha034(p: Panel) -> Frame:
    calm = stddev(p.returns, 2) / stddev(p.returns, 5)
    return rank((1 - rank(calm.replace([np.inf, -np.inf], np.nan))) + (1 - rank(delta(p.close, 1))))


# ((-1 * rank(Ts_Rank(close, 10))) * rank((close / open)))
def _alpha038(p: Panel) -> Frame:
    return -rank(ts_rank(p.close, 10)) * rank(p.close / p.open)


# ((-1 * rank(stddev(high, 10))) * correlation(high, volume, 10))
def _alpha040(p: Panel) -> Frame:
    return -rank(stddev(p.high, 10)) * correlation(p.high, p.volume, 10)


# (((high * low)^0.5) - vwap)
def _alpha041(p: Panel) -> Frame:
    return (p.high * p.low) ** 0.5 - p.vwap


# (rank((vwap - close)) / rank((vwap + close)))
def _alpha042(p: Panel) -> Frame:
    return rank(p.vwap - p.close) / rank(p.vwap + p.close)


# (-1 * correlation(high, rank(volume), 5))
def _alpha044(p: Panel) -> Frame:
    return -correlation(p.high, rank(p.volume), 5)


# (-1 * delta((((close - low) - (high - close)) / (close - low)), 9))
def _alpha053(p: Panel) -> Frame:
    position = ((p.close - p.low) - (p.high - p.close)) / (p.close - p.low)
    return -delta(position.replace([np.inf, -np.inf], np.nan), 9)


# ((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))
def _alpha054(p: Panel) -> Frame:
    return -((p.low - p.close) * p.open**5) / ((p.low - p.high) * p.close**5)


# ((close - open) / ((high - low) + .001))
def _alpha101(p: Panel) -> Frame:
    return (p.close - p.open) / (p.high - p.low + 0.001)


# --------------------------------------------------------------------------- #
# Second batch: the rest of the formulas that need only daily prices and volume.
# --------------------------------------------------------------------------- #


def _mix(x: Frame, y: Frame, weight: float) -> Frame:
    """The paper's ((x * weight) + (y * (1 - weight)))."""

    return x * weight + y * (1 - weight)


def _midpoint(p: Panel) -> Frame:
    return (p.high + p.low) / 2


# (rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)
def _alpha001(p: Panel) -> Frame:
    spread = stddev(p.returns, 20)
    base = choose(p.returns < 0, spread, p.close, p.returns, spread, p.close)
    return rank(ts_argmax(signed_power(base, 2.0), 5)) - 0.5


# 原式：((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : (-1 * 1))
# volume 换成当天的成交额：adv20 是平均成交额。
def _alpha007(p: Panel) -> Frame:
    move = delta(p.close, 7)
    active = -ts_rank(move.abs(), 60) * np.sign(move)
    return choose(p.adv(20) < p.amount, active, -1.0, p.adv(20), p.amount, active)


# (-1 * rank(((sum(open, 5) * sum(returns, 5)) - delay((sum(open, 5) * sum(returns, 5)), 10))))
def _alpha008(p: Panel) -> Frame:
    level = ts_sum(p.open, 5) * ts_sum(p.returns, 5)
    return -rank(level - delay(level, 10))


# 原式：(((-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1))) * rank(ts_rank((volume / adv20), 5)))
# volume 换成当天的成交额。
def _alpha017(p: Panel) -> Frame:
    return -rank(ts_rank(p.close, 10)) * rank(delta(delta(p.close, 1), 1)) * rank(ts_rank(p.amount / p.adv(20), 5))


# ((-1 * sign(((close - delay(close, 7)) + delta(close, 7)))) * (1 + rank((1 + sum(returns, 250)))))
def _alpha019(p: Panel) -> Frame:
    return -np.sign((p.close - delay(p.close, 7)) + delta(p.close, 7)) * (1 + rank(1 + ts_sum(p.returns, 250)))


# 原式见 FORMULAS；最后一层的 volume / adv20 换成 成交额 / adv20。
def _alpha021(p: Panel) -> Frame:
    long_mean, long_spread, short_mean = ts_sum(p.close, 8) / 8, stddev(p.close, 8), ts_sum(p.close, 2) / 2
    relative = p.amount / p.adv(20)
    busy = choose((relative > 1) | (relative == 1), 1.0, -1.0, relative)
    lower = choose(short_mean < long_mean - long_spread, 1.0, busy, short_mean, long_mean, long_spread, busy)
    return choose(long_mean + long_spread < short_mean, -1.0, lower, short_mean, long_mean, long_spread, lower)


# (-1 * (delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))))
def _alpha022(p: Panel) -> Frame:
    return -(delta(correlation(p.high, p.volume, 5), 5) * rank(stddev(p.close, 20)))


# ((((delta((sum(close, 100) / 100), 100) / delay(close, 100)) < 0.05) || (... == 0.05))
#   ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3)))
# 窗口 200 天：按当天的前复权价计算（价格先换到同一基准，差值再换回当天的基准）。
def _alpha024(p: Panel) -> Frame:
    close = p.adjusted(p.close)
    drift = delta(ts_sum(close, 100) / 100, 100) / delay(close, 100)
    near_low, recent = -p.on_today(close - ts_min(close, 100)), -p.on_today(delta(close, 3))
    return choose(drift <= 0.05, near_low, recent, drift, near_low, recent)


# (-1 * ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))
def _alpha026(p: Panel) -> Frame:
    return -ts_max(correlation(ts_rank(p.volume, 5), ts_rank(p.high, 5), 5), 3)


# ((0.5 < rank((sum(correlation(rank(volume), rank(vwap), 6), 2) / 2.0))) ? (-1 * 1) : 1)
def _alpha027(p: Panel) -> Frame:
    level = rank(ts_sum(correlation(rank(p.volume), rank(p.vwap), 6), 2) / 2.0)
    return choose(level > 0.5, -1.0, 1.0, level)


# scale(((correlation(adv20, low, 5) + ((high + low) / 2)) - close))
def _alpha028(p: Panel) -> Frame:
    return scale(correlation(p.adv(20), p.low, 5) + _midpoint(p) - p.close)


# (min(product(rank(rank(scale(log(sum(ts_min(rank(rank((-1 * rank(delta((close - 1), 5))))), 2), 1))))), 1), 5)
#   + ts_rank(delay((-1 * returns), 6), 5))
def _alpha029(p: Panel) -> Frame:
    inner = ts_sum(ts_min(rank(rank(-rank(delta(p.close - 1, 5)))), 2), 1)
    return ts_min(product(rank(rank(scale(np.log(inner)))), 1), 5) + ts_rank(delay(-p.returns, 6), 5)


# ((rank(rank(rank(decay_linear((-1 * rank(rank(delta(close, 10)))), 10)))) + rank((-1 * delta(close, 3))))
#   + sign(scale(correlation(adv20, low, 12))))
def _alpha031(p: Panel) -> Frame:
    first = rank(rank(rank(decay_linear(-rank(rank(delta(p.close, 10))), 10))))
    return first + rank(-delta(p.close, 3)) + np.sign(scale(correlation(p.adv(20), p.low, 12)))


# (scale(((sum(close, 7) / 7) - close)) + (20 * scale(correlation(vwap, delay(close, 5), 230))))
def _alpha032(p: Panel) -> Frame:
    close = p.adjusted(p.close)
    return (scale(p.on_today(ts_sum(close, 7) / 7 - close))
            + 20 * scale(correlation(p.adjusted(p.vwap), delay(close, 5), 230)))


# ((Ts_Rank(volume, 32) * (1 - Ts_Rank(((close + high) - low), 16))) * (1 - Ts_Rank(returns, 32)))
def _alpha035(p: Panel) -> Frame:
    return ts_rank(p.volume, 32) * (1 - ts_rank(p.close + p.high - p.low, 16)) * (1 - ts_rank(p.returns, 32))


# (((((2.21 * rank(correlation((close - open), delay(volume, 1), 15))) + (0.7 * rank((open - close))))
#   + (0.73 * rank(Ts_Rank(delay((-1 * returns), 6), 5)))) + rank(abs(correlation(vwap, adv20, 6))))
#   + (0.6 * rank((((sum(close, 200) / 200) - open) * (close - open)))))
def _alpha036(p: Panel) -> Frame:
    close, open_ = p.adjusted(p.close), p.adjusted(p.open)
    return (2.21 * rank(correlation(close - open_, delay(p.adjusted(p.volume, "volume"), 1), 15))
            + 0.7 * rank(p.open - p.close)
            + 0.73 * rank(ts_rank(delay(-p.returns, 6), 5))
            + rank(correlation(p.adjusted(p.vwap), p.adv(20), 6).abs())
            + 0.6 * rank(p.on_today(ts_sum(close, 200) / 200 - open_) * (p.close - p.open)))


# (rank(correlation(delay((open - close), 1), close, 200)) + rank((open - close)))
def _alpha037(p: Panel) -> Frame:
    close = p.adjusted(p.close)
    return rank(correlation(delay(p.adjusted(p.open) - close, 1), close, 200)) + rank(p.open - p.close)


# 原式：((-1 * rank((delta(close, 7) * (1 - rank(decay_linear((volume / adv20), 9)))))) * (1 + rank(sum(returns, 250))))
# volume 换成当天的成交额。
def _alpha039(p: Panel) -> Frame:
    activity = rank(decay_linear(p.amount / p.adv(20), 9))
    return -rank(delta(p.close, 7) * (1 - activity)) * (1 + rank(ts_sum(p.returns, 250)))


# 原式：(ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))，volume 换成当天的成交额。
def _alpha043(p: Panel) -> Frame:
    return ts_rank(p.amount / p.adv(20), 20) * ts_rank(-delta(p.close, 7), 8)


# (-1 * ((rank((sum(delay(close, 5), 20) / 20)) * correlation(close, volume, 2))
#   * rank(correlation(sum(close, 5), sum(close, 20), 2))))
def _alpha045(p: Panel) -> Frame:
    return -(rank(ts_sum(delay(p.close, 5), 20) / 20) * correlation(p.close, p.volume, 2)
             * rank(correlation(ts_sum(p.close, 5), ts_sum(p.close, 20), 2)))


def _slope_change(p: Panel) -> Frame:
    """(((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10))"""

    return (delay(p.close, 20) - delay(p.close, 10)) / 10 - (delay(p.close, 10) - p.close) / 10


# ((0.25 < x) ? (-1 * 1) : ((x < 0) ? 1 : ((-1 * 1) * (close - delay(close, 1)))))，x 为 _slope_change
def _alpha046(p: Panel) -> Frame:
    x, fallback = _slope_change(p), -(p.close - delay(p.close, 1))
    return choose(x > 0.25, -1.0, choose(x < 0, 1.0, fallback, x, fallback), x, fallback)


# 原式：((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) / (sum(high, 5) / 5)))
#   - rank((vwap - delay(vwap, 5))))，volume 换成当天的成交额。
def _alpha047(p: Panel) -> Frame:
    return (rank(1 / p.close) * p.amount / p.adv(20) * (p.high * rank(p.high - p.close)) / (ts_sum(p.high, 5) / 5)
            - rank(p.vwap - delay(p.vwap, 5)))


def _slope_rule(p: Panel, threshold: float) -> Frame:
    """((x < (-1 * threshold)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))，x 为 _slope_change"""

    x, fallback = _slope_change(p), -(p.close - delay(p.close, 1))
    return choose(x < -threshold, 1.0, fallback, x, fallback)


def _alpha049(p: Panel) -> Frame:
    return _slope_rule(p, 0.1)


# (-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5))
def _alpha050(p: Panel) -> Frame:
    return -ts_max(rank(correlation(rank(p.volume), rank(p.vwap), 5)), 5)


def _alpha051(p: Panel) -> Frame:
    return _slope_rule(p, 0.05)


# ((((-1 * ts_min(low, 5)) + delay(ts_min(low, 5), 5)) * rank(((sum(returns, 240) - sum(returns, 20)) / 220)))
#   * ts_rank(volume, 5))
def _alpha052(p: Panel) -> Frame:
    low5 = ts_min(p.low, 5)
    return ((-low5 + delay(low5, 5)) * rank((ts_sum(p.returns, 240) - ts_sum(p.returns, 20)) / 220)
            * ts_rank(p.volume, 5))


# (-1 * correlation(rank(((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12)))), rank(volume), 6))
def _alpha055(p: Panel) -> Frame:
    low12 = ts_min(p.low, 12)
    position = (p.close - low12) / (ts_max(p.high, 12) - low12)
    return -correlation(rank(position.replace([np.inf, -np.inf], np.nan)), rank(p.volume), 6)


# (0 - (1 * ((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))))
def _alpha057(p: Panel) -> Frame:
    return -((p.close - p.vwap) / decay_linear(rank(ts_argmax(p.close, 30)), 2))


# (0 - (1 * ((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) * volume))))
#   - scale(rank(ts_argmax(close, 10))))))
def _alpha060(p: Panel) -> Frame:
    pressure = ((p.close - p.low) - (p.high - p.close)) / (p.high - p.low) * p.volume
    return -(2 * scale(rank(pressure.replace([np.inf, -np.inf], np.nan))) - scale(rank(ts_argmax(p.close, 10))))


# (rank((vwap - ts_min(vwap, 16.1219))) < rank(correlation(vwap, adv180, 17.9282)))
def _alpha061(p: Panel) -> Frame:
    return less(rank(p.vwap - ts_min(p.vwap, 16.1219)), rank(correlation(p.vwap, p.adv(180), 17.9282)))


# ((rank(correlation(vwap, sum(adv20, 22.4101), 9.91009))
#   < rank(((rank(open) + rank(open)) < (rank(((high + low) / 2)) + rank(high))))) * -1)
def _alpha062(p: Panel) -> Frame:
    gap = less(rank(p.open) + rank(p.open), rank(_midpoint(p)) + rank(p.high))
    return less(rank(correlation(p.vwap, ts_sum(p.adv(20), 22.4101), 9.91009)), rank(gap)) * -1


# ((rank(correlation(sum(((open * 0.178404) + (low * (1 - 0.178404))), 12.7054), sum(adv120, 12.7054), 16.6208))
#   < rank(delta(((((high + low) / 2) * 0.178404) + (vwap * (1 - 0.178404))), 3.69741))) * -1)
def _alpha064(p: Panel) -> Frame:
    left = rank(correlation(ts_sum(_mix(p.open, p.low, 0.178404), 12.7054), ts_sum(p.adv(120), 12.7054), 16.6208))
    return less(left, rank(delta(_mix(_midpoint(p), p.vwap, 0.178404), 3.69741))) * -1


# ((rank(correlation(((open * 0.00817205) + (vwap * (1 - 0.00817205))), sum(adv60, 8.6911), 6.40374))
#   < rank((open - ts_min(open, 13.635)))) * -1)
def _alpha065(p: Panel) -> Frame:
    left = rank(correlation(_mix(p.open, p.vwap, 0.00817205), ts_sum(p.adv(60), 8.6911), 6.40374))
    return less(left, rank(p.open - ts_min(p.open, 13.635))) * -1


# ((rank(decay_linear(delta(vwap, 3.51013), 7.23052))
#   + Ts_Rank(decay_linear(((((low * 0.96633) + (low * (1 - 0.96633))) - vwap) / (open - ((high + low) / 2))), 11.4157), 6.72611)) * -1)
def _alpha066(p: Panel) -> Frame:
    stretch = (_mix(p.low, p.low, 0.96633) - p.vwap) / (p.open - _midpoint(p))
    stretch = stretch.replace([np.inf, -np.inf], np.nan)
    return (rank(decay_linear(delta(p.vwap, 3.51013), 7.23052)) + ts_rank(decay_linear(stretch, 11.4157), 6.72611)) * -1


# ((Ts_Rank(correlation(rank(high), rank(adv15), 8.91644), 13.9333)
#   < rank(delta(((close * 0.518371) + (low * (1 - 0.518371))), 1.06157))) * -1)
def _alpha068(p: Panel) -> Frame:
    left = ts_rank(correlation(rank(p.high), rank(p.adv(15)), 8.91644), 13.9333)
    return less(left, rank(delta(_mix(p.close, p.low, 0.518371), 1.06157))) * -1


# max(Ts_Rank(decay_linear(correlation(Ts_Rank(close, 3.43976), Ts_Rank(adv180, 12.0647), 18.0175), 4.20501), 15.6948),
#     Ts_Rank(decay_linear((rank(((low + open) - (vwap + vwap)))^2), 16.4662), 4.4388))
def _alpha071(p: Panel) -> Frame:
    first = ts_rank(decay_linear(correlation(ts_rank(p.close, 3.43976), ts_rank(p.adv(180), 12.0647), 18.0175), 4.20501), 15.6948)
    second = ts_rank(decay_linear(power(rank((p.low + p.open) - (p.vwap + p.vwap)), 2), 16.4662), 4.4388)
    return elementwise_max(first, second)


# (rank(decay_linear(correlation(((high + low) / 2), adv40, 8.93345), 10.1519))
#   / rank(decay_linear(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188), 6.86671), 2.95011)))
def _alpha072(p: Panel) -> Frame:
    top = rank(decay_linear(correlation(_midpoint(p), p.adv(40), 8.93345), 10.1519))
    bottom = rank(decay_linear(correlation(ts_rank(p.vwap, 3.72469), ts_rank(p.volume, 18.5188), 6.86671), 2.95011))
    return top / bottom


# (max(rank(decay_linear(delta(vwap, 4.72775), 2.91864)),
#   Ts_Rank(decay_linear(((delta(((open * 0.147155) + (low * (1 - 0.147155))), 2.03608)
#   / ((open * 0.147155) + (low * (1 - 0.147155)))) * -1), 3.33829), 16.7411)) * -1)
def _alpha073(p: Panel) -> Frame:
    base = _mix(p.open, p.low, 0.147155)
    second = ts_rank(decay_linear(delta(base, 2.03608) / base * -1, 3.33829), 16.7411)
    return elementwise_max(rank(decay_linear(delta(p.vwap, 4.72775), 2.91864)), second) * -1


# ((rank(correlation(close, sum(adv30, 37.4843), 15.1365))
#   < rank(correlation(rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11.4791))) * -1)
def _alpha074(p: Panel) -> Frame:
    left = rank(correlation(p.close, ts_sum(p.adv(30), 37.4843), 15.1365))
    right = rank(correlation(rank(_mix(p.high, p.vwap, 0.0261661)), rank(p.volume), 11.4791))
    return less(left, right) * -1


# (rank(correlation(vwap, volume, 4.24304)) < rank(correlation(rank(low), rank(adv50), 12.4413)))
def _alpha075(p: Panel) -> Frame:
    return less(rank(correlation(p.vwap, p.volume, 4.24304)), rank(correlation(rank(p.low), rank(p.adv(50)), 12.4413)))


# min(rank(decay_linear(((((high + low) / 2) + high) - (vwap + high)), 20.0451)),
#     rank(decay_linear(correlation(((high + low) / 2), adv40, 3.1614), 5.64125)))
def _alpha077(p: Panel) -> Frame:
    first = rank(decay_linear((_midpoint(p) + p.high) - (p.vwap + p.high), 20.0451))
    second = rank(decay_linear(correlation(_midpoint(p), p.adv(40), 3.1614), 5.64125))
    return elementwise_min(first, second)


# (rank(correlation(sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 19.7428), sum(adv40, 19.7428), 6.83313))
#   ^rank(correlation(rank(vwap), rank(volume), 5.77492)))
def _alpha078(p: Panel) -> Frame:
    base = rank(correlation(ts_sum(_mix(p.low, p.vwap, 0.352233), 19.7428), ts_sum(p.adv(40), 19.7428), 6.83313))
    return power(base, rank(correlation(rank(p.vwap), rank(p.volume), 5.77492)))


# ((rank(Log(product(rank((rank(correlation(vwap, sum(adv10, 49.6054), 8.47743))^4)), 14.9655)))
#   < rank(correlation(rank(vwap), rank(volume), 5.07914))) * -1)
def _alpha081(p: Panel) -> Frame:
    inner = rank(power(rank(correlation(p.vwap, ts_sum(p.adv(10), 49.6054), 8.47743)), 4))
    left = rank(np.log(product(inner, 14.9655)))
    return less(left, rank(correlation(rank(p.vwap), rank(p.volume), 5.07914))) * -1


# ((rank(delay(((high - low) / (sum(close, 5) / 5)), 2)) * rank(rank(volume)))
#   / (((high - low) / (sum(close, 5) / 5)) / (vwap - close)))
def _alpha083(p: Panel) -> Frame:
    width = (p.high - p.low) / (ts_sum(p.close, 5) / 5)
    return rank(delay(width, 2)) * rank(rank(p.volume)) / (width / (p.vwap - p.close))


# SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))
def _alpha084(p: Panel) -> Frame:
    return signed_power(ts_rank(p.vwap - ts_max(p.vwap, 15.3217), 20.7127), delta(p.close, 4.96796))


# (rank(correlation(((high * 0.876703) + (close * (1 - 0.876703))), adv30, 9.61331))
#   ^rank(correlation(Ts_Rank(((high + low) / 2), 3.70596), Ts_Rank(volume, 10.1595), 7.11408)))
def _alpha085(p: Panel) -> Frame:
    base = rank(correlation(_mix(p.high, p.close, 0.876703), p.adv(30), 9.61331))
    return power(base, rank(correlation(ts_rank(_midpoint(p), 3.70596), ts_rank(p.volume, 10.1595), 7.11408)))


# ((Ts_Rank(correlation(close, sum(adv20, 14.7444), 6.00049), 20.4195) < rank(((open + close) - (vwap + open)))) * -1)
def _alpha086(p: Panel) -> Frame:
    left = ts_rank(correlation(p.close, ts_sum(p.adv(20), 14.7444), 6.00049), 20.4195)
    return less(left, rank((p.open + p.close) - (p.vwap + p.open))) * -1


# min(rank(decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))), 8.06882)),
#     Ts_Rank(decay_linear(correlation(Ts_Rank(close, 8.44728), Ts_Rank(adv60, 20.6966), 8.01266), 6.65053), 2.61957))
def _alpha088(p: Panel) -> Frame:
    first = rank(decay_linear((rank(p.open) + rank(p.low)) - (rank(p.high) + rank(p.close)), 8.06882))
    second = ts_rank(decay_linear(correlation(ts_rank(p.close, 8.44728), ts_rank(p.adv(60), 20.6966), 8.01266), 6.65053), 2.61957)
    return elementwise_min(first, second)


# min(Ts_Rank(decay_linear(((((high + low) / 2) + close) < (low + open)), 14.7221), 18.8683),
#     Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 7.58555), 6.94024), 6.80584))
def _alpha092(p: Panel) -> Frame:
    first = ts_rank(decay_linear(less(_midpoint(p) + p.close, p.low + p.open), 14.7221), 18.8683)
    second = ts_rank(decay_linear(correlation(rank(p.low), rank(p.adv(30)), 7.58555), 6.94024), 6.80584)
    return elementwise_min(first, second)


# ((rank((vwap - ts_min(vwap, 11.5783)))^Ts_Rank(correlation(Ts_Rank(vwap, 19.6462), Ts_Rank(adv60, 4.02992), 18.0926), 2.70756)) * -1)
def _alpha094(p: Panel) -> Frame:
    exponent = ts_rank(correlation(ts_rank(p.vwap, 19.6462), ts_rank(p.adv(60), 4.02992), 18.0926), 2.70756)
    return power(rank(p.vwap - ts_min(p.vwap, 11.5783)), exponent) * -1


# (rank((open - ts_min(open, 12.4105)))
#   < Ts_Rank((rank(correlation(sum(((high + low) / 2), 19.1351), sum(adv40, 19.1351), 12.8742))^5), 11.7584))
def _alpha095(p: Panel) -> Frame:
    right = ts_rank(power(rank(correlation(ts_sum(_midpoint(p), 19.1351), ts_sum(p.adv(40), 19.1351), 12.8742)), 5), 11.7584)
    return less(rank(p.open - ts_min(p.open, 12.4105)), right)


# (max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume), 3.83878), 4.16783), 8.38151),
#   Ts_Rank(decay_linear(Ts_ArgMax(correlation(Ts_Rank(close, 7.45404), Ts_Rank(adv60, 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1)
def _alpha096(p: Panel) -> Frame:
    first = ts_rank(decay_linear(correlation(rank(p.vwap), rank(p.volume), 3.83878), 4.16783), 8.38151)
    peak = ts_argmax(correlation(ts_rank(p.close, 7.45404), ts_rank(p.adv(60), 4.13242), 3.65459), 12.6556)
    return elementwise_max(first, ts_rank(decay_linear(peak, 14.0365), 13.4143)) * -1


# (rank(decay_linear(correlation(vwap, sum(adv5, 26.4719), 4.58418), 7.18088))
#   - rank(decay_linear(Ts_Rank(Ts_ArgMin(correlation(rank(open), rank(adv15), 20.8187), 8.62571), 6.95668), 8.07206)))
def _alpha098(p: Panel) -> Frame:
    first = rank(decay_linear(correlation(p.vwap, ts_sum(p.adv(5), 26.4719), 4.58418), 7.18088))
    trough = ts_argmin(correlation(rank(p.open), rank(p.adv(15)), 20.8187), 8.62571)
    return first - rank(decay_linear(ts_rank(trough, 6.95668), 8.07206))


# ((rank(correlation(sum(((high + low) / 2), 19.8975), sum(adv60, 19.8975), 8.8136))
#   < rank(correlation(low, volume, 6.28259))) * -1)
def _alpha099(p: Panel) -> Frame:
    left = rank(correlation(ts_sum(_midpoint(p), 19.8975), ts_sum(p.adv(60), 19.8975), 8.8136))
    return less(left, rank(correlation(p.low, p.volume, 6.28259))) * -1


# --------------------------------------------------------------------------- #
# Third batch: the 18 formulas that compare a stock with its industry (IndNeutralize).
# ``p.neutralize`` is the same-day definition; ``p.neutralize_series`` is for a series that
# delta / correlation then read over a window.
# --------------------------------------------------------------------------- #


# (indneutralize(((correlation(delta(close, 1), delta(delay(close, 1), 1), 250) * delta(close, 1)) / close),
#   IndClass.subindustry) / sum(((delta(close, 1) / delay(close, 1))^2), 250))
# 窗口 250 天：按当天的前复权价计算；delta(close, 1) / delay(close, 1) 就是真实收益。
def _alpha048(p: Panel) -> Frame:
    close = p.adjusted(p.close)
    change = delta(close, 1)
    persistence = correlation(change, delay(change, 1), 250)
    return p.neutralize(persistence * change / close, "subindustry") / ts_sum(p.returns ** 2, 250)


# (-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.sector), volume, 3.92795), 7.89291), 5.50322))
def _alpha058(p: Panel) -> Frame:
    vwap = p.neutralize_series(p.vwap, "price", "sector")
    return -ts_rank(decay_linear(correlation(vwap, p.volume, 3.92795), 7.89291), 5.50322)


# (-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(((vwap * 0.728317) + (vwap * (1 - 0.728317))), IndClass.industry),
#   volume, 4.25197), 16.2289), 8.19648))
def _alpha059(p: Panel) -> Frame:
    vwap = p.neutralize_series(_mix(p.vwap, p.vwap, 0.728317), "price", "industry")
    return -ts_rank(decay_linear(correlation(vwap, p.volume, 4.25197), 16.2289), 8.19648)


# ((rank(decay_linear(delta(IndNeutralize(close, IndClass.industry), 2.25164), 8.22237))
#   - rank(decay_linear(correlation(((vwap * 0.318108) + (open * (1 - 0.318108))), sum(adv180, 37.2467), 13.557), 12.2883))) * -1)
def _alpha063(p: Panel) -> Frame:
    first = rank(decay_linear(delta(p.neutralize_series(p.close, "price", "industry"), 2.25164), 8.22237))
    second = rank(decay_linear(correlation(_mix(p.vwap, p.open, 0.318108), ts_sum(p.adv(180), 37.2467), 13.557), 12.2883))
    return (first - second) * -1


# ((rank((high - ts_min(high, 2.14593)))^rank(correlation(IndNeutralize(vwap, IndClass.sector),
#   IndNeutralize(adv20, IndClass.subindustry), 6.02936))) * -1)
def _alpha067(p: Panel) -> Frame:
    pair = correlation(p.neutralize_series(p.vwap, "price", "sector"),
                       p.neutralize_series(p.adv(20), "amount", "subindustry"), 6.02936)
    return power(rank(p.high - ts_min(p.high, 2.14593)), rank(pair)) * -1


# ((rank(ts_max(delta(IndNeutralize(vwap, IndClass.industry), 2.72412), 4.79344))
#   ^Ts_Rank(correlation(((close * 0.490655) + (vwap * (1 - 0.490655))), adv20, 4.92416), 9.0615)) * -1)
def _alpha069(p: Panel) -> Frame:
    base = rank(ts_max(delta(p.neutralize_series(p.vwap, "price", "industry"), 2.72412), 4.79344))
    return power(base, ts_rank(correlation(_mix(p.close, p.vwap, 0.490655), p.adv(20), 4.92416), 9.0615)) * -1


# ((rank(delta(vwap, 1.29456))^Ts_Rank(correlation(IndNeutralize(close, IndClass.industry), adv50, 17.8256), 17.9171)) * -1)
def _alpha070(p: Panel) -> Frame:
    exponent = ts_rank(correlation(p.neutralize_series(p.close, "price", "industry"), p.adv(50), 17.8256), 17.9171)
    return power(rank(delta(p.vwap, 1.29456)), exponent) * -1


# (max(rank(decay_linear(delta(vwap, 1.24383), 11.8259)),
#   Ts_Rank(decay_linear(Ts_Rank(correlation(IndNeutralize(low, IndClass.sector), adv81, 8.14941), 19.569), 17.1543), 19.383)) * -1)
def _alpha076(p: Panel) -> Frame:
    low = p.neutralize_series(p.low, "price", "sector")
    second = ts_rank(decay_linear(ts_rank(correlation(low, p.adv(81), 8.14941), 19.569), 17.1543), 19.383)
    return elementwise_max(rank(decay_linear(delta(p.vwap, 1.24383), 11.8259)), second) * -1


# (rank(delta(IndNeutralize(((close * 0.60733) + (open * (1 - 0.60733))), IndClass.sector), 1.23438))
#   < rank(correlation(Ts_Rank(vwap, 3.60973), Ts_Rank(adv150, 9.18637), 14.6644)))
def _alpha079(p: Panel) -> Frame:
    left = rank(delta(p.neutralize_series(_mix(p.close, p.open, 0.60733), "price", "sector"), 1.23438))
    return less(left, rank(correlation(ts_rank(p.vwap, 3.60973), ts_rank(p.adv(150), 9.18637), 14.6644)))


# ((rank(Sign(delta(IndNeutralize(((open * 0.868128) + (high * (1 - 0.868128))), IndClass.industry), 4.04545)))
#   ^Ts_Rank(correlation(high, adv10, 5.11456), 5.53756)) * -1)
def _alpha080(p: Panel) -> Frame:
    base = rank(np.sign(delta(p.neutralize_series(_mix(p.open, p.high, 0.868128), "price", "industry"), 4.04545)))
    return power(base, ts_rank(correlation(p.high, p.adv(10), 5.11456), 5.53756)) * -1


# (min(rank(decay_linear(delta(open, 1.46063), 14.8717)),
#   Ts_Rank(decay_linear(correlation(IndNeutralize(volume, IndClass.sector), ((open * 0.634196) + (open * (1 - 0.634196))), 17.4842),
#   6.92131), 13.4283)) * -1)
def _alpha082(p: Panel) -> Frame:
    volume = p.neutralize_series(p.volume, "volume", "sector")
    second = ts_rank(decay_linear(correlation(volume, _mix(p.open, p.open, 0.634196), 17.4842), 6.92131), 13.4283)
    return elementwise_min(rank(decay_linear(delta(p.open, 1.46063), 14.8717)), second) * -1


# (max(rank(decay_linear(delta(((close * 0.369701) + (vwap * (1 - 0.369701))), 1.91233), 2.65461)),
#   Ts_Rank(decay_linear(abs(correlation(IndNeutralize(adv81, IndClass.industry), close, 13.4132)), 4.89768), 14.4535)) * -1)
def _alpha087(p: Panel) -> Frame:
    first = rank(decay_linear(delta(_mix(p.close, p.vwap, 0.369701), 1.91233), 2.65461))
    pair = correlation(p.neutralize_series(p.adv(81), "amount", "industry"), p.close, 13.4132)
    return elementwise_max(first, ts_rank(decay_linear(pair.abs(), 4.89768), 14.4535)) * -1


# (Ts_Rank(decay_linear(correlation(((low * 0.967285) + (low * (1 - 0.967285))), adv10, 6.94279), 5.51607), 3.79744)
#   - Ts_Rank(decay_linear(delta(IndNeutralize(vwap, IndClass.industry), 3.48158), 10.1466), 15.3012))
def _alpha089(p: Panel) -> Frame:
    first = ts_rank(decay_linear(correlation(_mix(p.low, p.low, 0.967285), p.adv(10), 6.94279), 5.51607), 3.79744)
    second = ts_rank(decay_linear(delta(p.neutralize_series(p.vwap, "price", "industry"), 3.48158), 10.1466), 15.3012)
    return first - second


# ((rank((close - ts_max(close, 4.66719)))^Ts_Rank(correlation(IndNeutralize(adv40, IndClass.subindustry), low, 5.38375), 3.21856)) * -1)
def _alpha090(p: Panel) -> Frame:
    exponent = ts_rank(correlation(p.neutralize_series(p.adv(40), "amount", "subindustry"), p.low, 5.38375), 3.21856)
    return power(rank(p.close - ts_max(p.close, 4.66719)), exponent) * -1


# ((Ts_Rank(decay_linear(decay_linear(correlation(IndNeutralize(close, IndClass.industry), volume, 9.74928), 16.398), 3.83219), 4.8667)
#   - rank(decay_linear(correlation(vwap, adv30, 4.01303), 2.6809))) * -1)
def _alpha091(p: Panel) -> Frame:
    pair = correlation(p.neutralize_series(p.close, "price", "industry"), p.volume, 9.74928)
    first = ts_rank(decay_linear(decay_linear(pair, 16.398), 3.83219), 4.8667)
    return (first - rank(decay_linear(correlation(p.vwap, p.adv(30), 4.01303), 2.6809))) * -1


# (Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.industry), adv81, 17.4193), 19.848), 7.54455)
#   / rank(decay_linear(delta(((close * 0.524434) + (vwap * (1 - 0.524434))), 2.77377), 16.2664)))
def _alpha093(p: Panel) -> Frame:
    top = ts_rank(decay_linear(correlation(p.neutralize_series(p.vwap, "price", "industry"), p.adv(81), 17.4193), 19.848), 7.54455)
    return top / rank(decay_linear(delta(_mix(p.close, p.vwap, 0.524434), 2.77377), 16.2664))


# ((rank(decay_linear(delta(IndNeutralize(((low * 0.721001) + (vwap * (1 - 0.721001))), IndClass.industry), 3.3705), 20.4523))
#   - Ts_Rank(decay_linear(Ts_Rank(correlation(Ts_Rank(low, 7.87871), Ts_Rank(adv60, 17.255), 4.97547), 18.5925), 15.7152), 6.71659)) * -1)
def _alpha097(p: Panel) -> Frame:
    first = rank(decay_linear(delta(p.neutralize_series(_mix(p.low, p.vwap, 0.721001), "price", "industry"), 3.3705), 20.4523))
    pair = correlation(ts_rank(p.low, 7.87871), ts_rank(p.adv(60), 17.255), 4.97547)
    return (first - ts_rank(decay_linear(ts_rank(pair, 18.5925), 15.7152), 6.71659)) * -1


# (0 - (1 * (((1.5 * scale(indneutralize(indneutralize(rank(((((close - low) - (high - close)) / (high - low)) * volume)),
#   IndClass.subindustry), IndClass.subindustry))) - scale(indneutralize((correlation(close, rank(adv20), 5)
#   - rank(ts_argmin(close, 30))), IndClass.subindustry))) * (volume / adv20))))
# 最后的 volume / adv20 换成 成交额 / adv20。
def _alpha100(p: Panel) -> Frame:
    pressure = (((p.close - p.low) - (p.high - p.close)) / (p.high - p.low) * p.volume).replace([np.inf, -np.inf], np.nan)
    first = scale(p.neutralize(p.neutralize(rank(pressure), "subindustry"), "subindustry"))
    trend = correlation(p.close, rank(p.adv(20)), 5) - rank(ts_argmin(p.close, 30))
    second = scale(p.neutralize(trend, "subindustry"))
    return -((1.5 * first - second) * (p.amount / p.adv(20)))


_OHLC = ("raw_open", "raw_high", "raw_low", "raw_close")


@dataclass(frozen=True)
class _Formula:
    number: int
    title: str
    category: str
    # 窗口跨过的相邻交易日步数；只用当天数据或只用收益率的公式为 0。
    span: int
    # 算出第一个值需要的交易日数。
    history: int
    fields: tuple[str, ...]
    formula: str
    func: Callable[[Panel], Frame]

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        panel = Panel(bars)
        members = None
        if UNIVERSE_COLUMN in bars.columns:
            members = pivot_field(bars.assign(**{UNIVERSE_COLUMN: bars[UNIVERSE_COLUMN].astype(float)}), UNIVERSE_COLUMN).eq(1.0)
        token = _UNIVERSE.set(members)
        try:
            values = self.func(panel).replace([np.inf, -np.inf], np.nan)
        finally:
            _UNIVERSE.reset(token)
        return melt_wide(panel.comparable(values, self.span))


FORMULAS: tuple[_Formula, ...] = (
    _Formula(2, "量变排名与日内涨幅相关性", "量价", 7, 8, ("raw_open", "raw_close", "volume"),
             "-correlation(rank(delta(log(volume), 2)), rank((close - open) / open), 6)", _alpha002),
    _Formula(3, "开盘价排名与成交量排名相关性", "量价", 9, 10, ("raw_open", "volume"),
             "-correlation(rank(open), rank(volume), 10)", _alpha003),
    _Formula(4, "最低价排名的时序位置", "反转", 8, 9, ("raw_low",), "-ts_rank(rank(low), 9)", _alpha004),
    _Formula(5, "开盘与收盘相对成交均价的位置", "量价", 9, 10, ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "amount"),
             "rank(open - sum(vwap, 10) / 10) * -abs(rank(close - vwap))", _alpha005),
    _Formula(6, "开盘价与成交量相关性", "量价", 9, 10, ("raw_open", "volume"), "-correlation(open, volume, 10)", _alpha006),
    _Formula(9, "连续同向时的日价格变化", "动量", 5, 6, ("raw_close",),
             "ts_min(delta(close, 1), 5) > 0 或 ts_max(delta(close, 1), 5) < 0 时取 delta(close, 1)，否则取其相反数", _alpha009),
    _Formula(10, "连续同向时的日价格变化排名", "动量", 4, 5, ("raw_close",),
             "rank(ts_min(delta(close, 1), 4) > 0 或 ts_max(delta(close, 1), 4) < 0 时取 delta(close, 1)，否则取其相反数)", _alpha010),
    _Formula(11, "均价收盘差的极值与量变", "量价", 3, 4, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "(rank(ts_max(vwap - close, 3)) + rank(ts_min(vwap - close, 3))) * rank(delta(volume, 3))", _alpha011),
    _Formula(12, "量变方向与价格变化", "量价", 1, 2, ("raw_close", "volume"), "sign(delta(volume, 1)) * -delta(close, 1)", _alpha012),
    _Formula(13, "收盘价排名与成交量排名的协方差", "量价", 4, 5, ("raw_close", "volume"),
             "-rank(covariance(rank(close), rank(volume), 5))", _alpha013),
    _Formula(14, "收益变化与开盘量价相关性", "量价", 9, 10, ("raw_open", "raw_close", "volume"),
             "-rank(delta(returns, 3)) * correlation(open, volume, 10)", _alpha014),
    _Formula(15, "最高价排名与成交量排名相关性的累计", "量价", 4, 5, ("raw_high", "volume"),
             "-sum(rank(correlation(rank(high), rank(volume), 3)), 3)", _alpha015),
    _Formula(16, "最高价排名与成交量排名的协方差", "量价", 4, 5, ("raw_high", "volume"),
             "-rank(covariance(rank(high), rank(volume), 5))", _alpha016),
    _Formula(18, "K线实体波动与开收相关性", "K线", 9, 10, ("raw_open", "raw_close"),
             "-rank(stddev(abs(close - open), 5) + (close - open) + correlation(close, open, 10))", _alpha018),
    _Formula(20, "开盘价相对昨日高收低的缺口", "K线", 1, 2, _OHLC,
             "-rank(open - delay(high, 1)) * rank(open - delay(close, 1)) * rank(open - delay(low, 1))", _alpha020),
    _Formula(23, "高于20日均高时的两日最高价变化", "反转", 19, 20, ("raw_high",),
             "sum(high, 20) / 20 < high 时取 -delta(high, 2)，否则取 0", _alpha023),
    _Formula(25, "收益、成交额、均价与上影线", "量价", 0, 20, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "rank(-returns * adv20 * vwap * (high - close))", _alpha025),
    _Formula(30, "三日涨跌方向与量能比", "量价", 19, 20, ("raw_close", "volume"),
             "(1 - rank(sign(delta(close, 1)) + sign(delay(delta(close, 1), 1)) + sign(delay(delta(close, 1), 2)))) * sum(volume, 5) / sum(volume, 20)", _alpha030),
    _Formula(33, "开收盘比例截面排名", "反转", 0, 1, ("raw_open", "raw_close"), "rank(open / close - 1)", _alpha033),
    _Formula(34, "短长期波动比与日价格变化", "波动", 1, 6, ("raw_close",),
             "rank((1 - rank(stddev(returns, 2) / stddev(returns, 5))) + (1 - rank(delta(close, 1))))", _alpha034),
    _Formula(38, "收盘价时序位置与日内涨幅", "反转", 9, 10, ("raw_open", "raw_close"),
             "-rank(ts_rank(close, 10)) * rank(close / open)", _alpha038),
    _Formula(40, "最高价波动与量价相关性", "量价", 9, 10, ("raw_high", "volume"),
             "-rank(stddev(high, 10)) * correlation(high, volume, 10)", _alpha040),
    _Formula(41, "高低价几何均值减成交均价", "K线", 0, 1, ("raw_high", "raw_low", "volume", "amount"), "(high * low)^0.5 - vwap", _alpha041),
    _Formula(42, "均价收盘之差与之和的排名比", "K线", 0, 1, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "rank(vwap - close) / rank(vwap + close)", _alpha042),
    _Formula(44, "最高价与成交量排名相关性", "量价", 4, 5, ("raw_high", "volume"), "-correlation(high, rank(volume), 5)", _alpha044),
    _Formula(53, "收盘在日内区间位置的9日变化", "K线", 0, 10, ("raw_high", "raw_low", "raw_close"),
             "-delta(((close - low) - (high - close)) / (close - low), 9)", _alpha053),
    _Formula(54, "日内位置与开收比的五次方", "K线", 0, 1, _OHLC,
             "-((low - close) * open^5) / ((low - high) * close^5)", _alpha054),
    _Formula(101, "K线实体占振幅比例", "K线", 0, 1, _OHLC, "(close - open) / (high - low + 0.001)", _alpha101),
)


_C = ("raw_close",)
_V = ("raw_high", "raw_low", "volume", "amount")      # vwap 要用到的列
_ALL = ("raw_open", "raw_high", "raw_low", "raw_close", "volume", "amount")
_AMOUNT_NOTE = "（volume 换成当天的成交额 amount，单位才和 adv 一致）"
# 窗口超过 200 个交易日：A股多数股票每年分红一次，窗口几乎总会跨过除息日，所以按当天的前复权价计算。
_LONG_NOTE = "（窗口很长，每天都按当天的前复权价计算，所以跨过除权除息日也有值）"
_SPARSE_NOTE = "（内层 3 天的相关系数里，成交额的 4 日排名常常几天不变，相关系数没有定义，多数日子没有值）"
_SPARSE_NOTE_97 = "（内层 4 天的相关系数里，60 日平均成交额的 17 日排名常常几天不变，相关系数没有定义，多数日子没有值）"

# 编号, 名称, 类别, span（价量窗口跨过的相邻交易日步数）, history（算出第一个值需要的交易日数）, 用到的列, 公式。
_SECOND_BATCH: tuple[_Formula, ...] = (
    _Formula(1, "收益为负时的波动与价格的高点位置", "波动", 4, 25, _C,
             "rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5", _alpha001),
    _Formula(7, "放量时的7日价格变化排名", "量价", 66, 67, ("raw_close", "amount"),
             "(adv20 < volume) ? (-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7)) : -1" + _AMOUNT_NOTE, _alpha007),
    _Formula(8, "开盘价与收益乘积的10日变化", "动量", 14, 16, ("raw_open", "raw_close"),
             "-rank((sum(open, 5) * sum(returns, 5)) - delay(sum(open, 5) * sum(returns, 5), 10))", _alpha008),
    _Formula(17, "收盘价位置、价格加速度与相对成交额", "量价", 9, 24, ("raw_close", "amount"),
             "-rank(ts_rank(close, 10)) * rank(delta(delta(close, 1), 1)) * rank(ts_rank(volume / adv20, 5))" + _AMOUNT_NOTE, _alpha017),
    _Formula(19, "7日价格方向与年度累计收益", "动量", 7, 251, _C,
             "-sign((close - delay(close, 7)) + delta(close, 7)) * (1 + rank(1 + sum(returns, 250)))", _alpha019),
    _Formula(21, "均线通道突破与相对成交额", "量价", 7, 20, ("raw_close", "amount"),
             "(sum(close, 8) / 8 + stddev(close, 8)) < sum(close, 2) / 2 ? -1 : (sum(close, 2) / 2 < sum(close, 8) / 8 - stddev(close, 8) ? 1 : "
             "((1 < volume / adv20) || (volume / adv20 == 1) ? 1 : -1))" + _AMOUNT_NOTE, _alpha021),
    _Formula(22, "量价相关性变化与价格波动", "量价", 19, 20, ("raw_high", "raw_close", "volume"),
             "-(delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20)))", _alpha022),
    _Formula(24, "百日均线变化慢时看距百日低点，否则看3日变化", "反转", 0, 200, _C,
             "((delta(sum(close, 100) / 100, 100) / delay(close, 100)) <= 0.05) ? -(close - ts_min(close, 100)) : -delta(close, 3)" + _LONG_NOTE, _alpha024),
    _Formula(26, "成交量与最高价时序排名的相关性高点", "量价", 10, 11, ("raw_high", "volume"),
             "-ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3)", _alpha026),
    _Formula(27, "量价排名相关性是否偏高", "量价", 6, 7, _V,
             "(0.5 < rank(sum(correlation(rank(volume), rank(vwap), 6), 2) / 2.0)) ? -1 : 1", _alpha027),
    _Formula(28, "成交额与最低价相关性加中间价减收盘价", "量价", 4, 24, ("raw_high", "raw_low", "raw_close", "amount"),
             "scale((correlation(adv20, low, 5) + (high + low) / 2) - close)", _alpha028),
    _Formula(29, "5日价格变化的多层排名与滞后收益", "反转", 10, 12, _C,
             "min(product(rank(rank(scale(log(sum(ts_min(rank(rank(-rank(delta(close - 1, 5)))), 2), 1))))), 1), 5) "
             "+ ts_rank(delay(-returns, 6), 5)", _alpha029),
    _Formula(31, "10日价格变化的衰减排名与短期反转", "反转", 19, 31, ("raw_low", "raw_close", "amount"),
             "rank(rank(rank(decay_linear(-rank(rank(delta(close, 10))), 10)))) + rank(-delta(close, 3)) "
             "+ sign(scale(correlation(adv20, low, 12)))", _alpha031),
    _Formula(32, "收盘价偏离7日均线与长期均价相关性", "反转", 0, 235, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "scale(sum(close, 7) / 7 - close) + 20 * scale(correlation(vwap, delay(close, 5), 230))" + _LONG_NOTE, _alpha032),
    _Formula(35, "成交量、价格区间与收益的时序位置", "量价", 31, 33, ("raw_high", "raw_low", "raw_close", "volume"),
             "Ts_Rank(volume, 32) * (1 - Ts_Rank((close + high) - low, 16)) * (1 - Ts_Rank(returns, 32))", _alpha035),
    _Formula(36, "五项量价特征的加权组合", "量价", 0, 200, _ALL,
             "2.21 * rank(correlation(close - open, delay(volume, 1), 15)) + 0.7 * rank(open - close) "
             "+ 0.73 * rank(Ts_Rank(delay(-returns, 6), 5)) + rank(abs(correlation(vwap, adv20, 6))) "
             "+ 0.6 * rank((sum(close, 200) / 200 - open) * (close - open))" + _LONG_NOTE, _alpha036),
    _Formula(37, "昨日K线实体与收盘价的长期相关性", "K线", 0, 201, ("raw_open", "raw_close"),
             "rank(correlation(delay(open - close, 1), close, 200)) + rank(open - close)" + _LONG_NOTE, _alpha037),
    _Formula(39, "7日价格变化、相对成交额与年度收益", "动量", 7, 251, ("raw_close", "amount"),
             "-rank(delta(close, 7) * (1 - rank(decay_linear(volume / adv20, 9)))) * (1 + rank(sum(returns, 250)))" + _AMOUNT_NOTE, _alpha039),
    _Formula(43, "相对成交额与7日跌幅的时序位置", "量价", 14, 39, ("raw_close", "amount"),
             "ts_rank(volume / adv20, 20) * ts_rank(-delta(close, 7), 8)" + _AMOUNT_NOTE, _alpha043),
    _Formula(45, "滞后均价与两组量价相关性", "量价", 24, 25, ("raw_close", "volume"),
             "-(rank(sum(delay(close, 5), 20) / 20) * correlation(close, volume, 2) * rank(correlation(sum(close, 5), sum(close, 20), 2)))", _alpha045),
    _Formula(46, "前后10日价格斜率之差（阈值 0.25）", "反转", 20, 21, _C,
             "x = (delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10；"
             "0.25 < x ? -1 : (x < 0 ? 1 : -(close - delay(close, 1)))", _alpha046),
    _Formula(47, "低价、相对成交额、上影线与均价变化", "量价", 5, 20, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "rank(1 / close) * volume / adv20 * (high * rank(high - close)) / (sum(high, 5) / 5) - rank(vwap - delay(vwap, 5))" + _AMOUNT_NOTE, _alpha047),
    _Formula(49, "前后10日价格斜率之差（阈值 -0.1）", "反转", 20, 21, _C,
             "x = (delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10；x < -0.1 ? 1 : -(close - delay(close, 1))", _alpha049),
    _Formula(50, "成交量与均价排名相关性的5日高点", "量价", 8, 9, _V,
             "-ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5)", _alpha050),
    _Formula(51, "前后10日价格斜率之差（阈值 -0.05）", "反转", 20, 21, _C,
             "x = (delay(close, 20) - delay(close, 10)) / 10 - (delay(close, 10) - close) / 10；x < -0.05 ? 1 : -(close - delay(close, 1))", _alpha051),
    _Formula(52, "最低价回升、中长期收益与成交量位置", "动量", 9, 241, ("raw_low", "raw_close", "volume"),
             "(-ts_min(low, 5) + delay(ts_min(low, 5), 5)) * rank((sum(returns, 240) - sum(returns, 20)) / 220) * ts_rank(volume, 5)", _alpha052),
    _Formula(55, "12日价格位置与成交量的排名相关性", "量价", 16, 17, ("raw_high", "raw_low", "raw_close", "volume"),
             "-correlation(rank((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12))), rank(volume), 6)", _alpha055),
    _Formula(57, "收盘价偏离均价与30日高点位置", "反转", 30, 31, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "-((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))", _alpha057),
    _Formula(60, "日内买卖力量与10日高点位置", "量价", 9, 10, ("raw_high", "raw_low", "raw_close", "volume"),
             "-(2 * scale(rank(((close - low) - (high - close)) / (high - low) * volume)) - scale(rank(ts_argmax(close, 10))))", _alpha060),
    _Formula(61, "均价离低点的位置与长期成交额相关性比较", "量价", 16, 196, _V,
             "rank(vwap - ts_min(vwap, 16.1219)) < rank(correlation(vwap, adv180, 17.9282))", _alpha061),
    _Formula(62, "均价与成交额相关性和开盘价位置比较", "量价", 8, 49, ("raw_open", "raw_high", "raw_low", "volume", "amount"),
             "(rank(correlation(vwap, sum(adv20, 22.4101), 9.91009)) < rank((rank(open) + rank(open)) < (rank((high + low) / 2) + rank(high)))) * -1", _alpha062),
    _Formula(64, "开低价与成交额相关性和中间价变化比较", "量价", 26, 146, ("raw_open", "raw_high", "raw_low", "volume", "amount"),
             "(rank(correlation(sum(open * 0.178404 + low * (1 - 0.178404), 12.7054), sum(adv120, 12.7054), 16.6208)) "
             "< rank(delta(((high + low) / 2) * 0.178404 + vwap * (1 - 0.178404), 3.69741))) * -1", _alpha064),
    _Formula(65, "开盘价与成交额相关性和开盘离低点比较", "量价", 12, 72, ("raw_open", "raw_high", "raw_low", "volume", "amount"),
             "(rank(correlation(open * 0.00817205 + vwap * (1 - 0.00817205), sum(adv60, 8.6911), 6.40374)) < rank(open - ts_min(open, 13.635))) * -1", _alpha065),
    _Formula(66, "均价变化与开盘偏离中间价", "K线", 15, 16, ("raw_open", "raw_high", "raw_low", "volume", "amount"),
             "(rank(decay_linear(delta(vwap, 3.51013), 7.23052)) + Ts_Rank(decay_linear((low * 0.96633 + low * (1 - 0.96633) - vwap) "
             "/ (open - (high + low) / 2), 11.4157), 6.72611)) * -1", _alpha066),
    _Formula(68, "最高价与成交额相关性和收盘低价变化比较", "量价", 19, 34, ("raw_high", "raw_low", "raw_close", "amount"),
             "(Ts_Rank(correlation(rank(high), rank(adv15), 8.91644), 13.9333) < rank(delta(close * 0.518371 + low * (1 - 0.518371), 1.06157))) * -1", _alpha068),
    _Formula(71, "收盘与成交额的时序相关性和开低价偏离均价取大", "量价", 36, 225, _ALL,
             "max(Ts_Rank(decay_linear(correlation(Ts_Rank(close, 3.43976), Ts_Rank(adv180, 12.0647), 18.0175), 4.20501), 15.6948), "
             "Ts_Rank(decay_linear(rank((low + open) - (vwap + vwap))^2, 16.4662), 4.4388))", _alpha071),
    _Formula(72, "中间价与成交额相关性比量价时序相关性", "量价", 23, 56, _V,
             "rank(decay_linear(correlation((high + low) / 2, adv40, 8.93345), 10.1519)) "
             "/ rank(decay_linear(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188), 6.86671), 2.95011))", _alpha072),
    _Formula(73, "均价变化与开低价跌幅取大", "动量", 19, 20, ("raw_open", "raw_high", "raw_low", "volume", "amount"),
             "max(rank(decay_linear(delta(vwap, 4.72775), 2.91864)), Ts_Rank(decay_linear(-(delta(open * 0.147155 + low * (1 - 0.147155), 2.03608) "
             "/ (open * 0.147155 + low * (1 - 0.147155))), 3.33829), 16.7411)) * -1", _alpha073),
    _Formula(74, "收盘与成交额相关性和高价均价与成交量相关性比较", "量价", 14, 80, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "(rank(correlation(close, sum(adv30, 37.4843), 15.1365)) < rank(correlation(rank(high * 0.0261661 + vwap * (1 - 0.0261661)), rank(volume), 11.4791))) * -1", _alpha074),
    _Formula(75, "均价与成交量相关性和最低价与成交额相关性比较", "量价", 11, 61, _V,
             "rank(correlation(vwap, volume, 4.24304)) < rank(correlation(rank(low), rank(adv50), 12.4413))", _alpha075),
    _Formula(77, "中间价偏离均价与中间价成交额相关性取小", "量价", 19, 46, _V,
             "min(rank(decay_linear(((high + low) / 2 + high) - (vwap + high), 20.0451)), "
             "rank(decay_linear(correlation((high + low) / 2, adv40, 3.1614), 5.64125)))", _alpha077),
    _Formula(78, "低价均价与成交额相关性的量价相关性次方", "量价", 23, 63, _V,
             "rank(correlation(sum(low * 0.352233 + vwap * (1 - 0.352233), 19.7428), sum(adv40, 19.7428), 6.83313))"
             "^rank(correlation(rank(vwap), rank(volume), 5.77492))", _alpha078),
    _Formula(81, "均价与成交额相关性的累乘和量价相关性比较", "量价", 20, 78, _V,
             "(rank(Log(product(rank(rank(correlation(vwap, sum(adv10, 49.6054), 8.47743))^4), 14.9655))) "
             "< rank(correlation(rank(vwap), rank(volume), 5.07914))) * -1", _alpha081),
    _Formula(83, "振幅、成交量与均价收盘差", "波动", 6, 7, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "rank(delay((high - low) / (sum(close, 5) / 5), 2)) * rank(rank(volume)) / (((high - low) / (sum(close, 5) / 5)) / (vwap - close))", _alpha083),
    _Formula(84, "均价离高点位置的价格变化次方", "动量", 33, 34, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "SignedPower(Ts_Rank(vwap - ts_max(vwap, 15.3217), 20.7127), delta(close, 4.96796))", _alpha084),
    _Formula(85, "高收价与成交额相关性的量价时序相关性次方", "量价", 15, 38, ("raw_high", "raw_low", "raw_close", "volume", "amount"),
             "rank(correlation(high * 0.876703 + close * (1 - 0.876703), adv30, 9.61331))"
             "^rank(correlation(Ts_Rank((high + low) / 2, 3.70596), Ts_Rank(volume, 10.1595), 7.11408))", _alpha085),
    _Formula(86, "收盘与成交额相关性位置和收盘偏离均价比较", "量价", 24, 57, _ALL,
             "(Ts_Rank(correlation(close, sum(adv20, 14.7444), 6.00049), 20.4195) < rank((open + close) - (vwap + open))) * -1", _alpha086),
    _Formula(88, "开低与高收排名差和收盘成交额时序相关性取小", "量价", 20, 92, ("raw_open", "raw_high", "raw_low", "raw_close", "amount"),
             "min(rank(decay_linear((rank(open) + rank(low)) - (rank(high) + rank(close)), 8.06882)), "
             "Ts_Rank(decay_linear(correlation(Ts_Rank(close, 8.44728), Ts_Rank(adv60, 20.6966), 8.01266), 6.65053), 2.61957))", _alpha088),
    _Formula(92, "中间价加收盘是否低于开低价与低价成交额相关性取小", "K线", 30, 46, ("raw_open", "raw_high", "raw_low", "raw_close", "amount"),
             "min(Ts_Rank(decay_linear(((high + low) / 2 + close) < (low + open), 14.7221), 18.8683), "
             "Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 7.58555), 6.94024), 6.80584))", _alpha092),
    _Formula(94, "均价离低点位置的量价时序相关性次方", "量价", 36, 81, _V,
             "(rank(vwap - ts_min(vwap, 11.5783))^Ts_Rank(correlation(Ts_Rank(vwap, 19.6462), Ts_Rank(adv60, 4.02992), 18.0926), 2.70756)) * -1", _alpha094),
    _Formula(95, "开盘离低点和中间价成交额相关性比较", "量价", 39, 79, ("raw_open", "raw_high", "raw_low", "amount"),
             "rank(open - ts_min(open, 12.4105)) < Ts_Rank(rank(correlation(sum((high + low) / 2, 19.1351), sum(adv40, 19.1351), 12.8742))^5, 11.7584)", _alpha095),
    _Formula(96, "量价相关性和收盘成交额相关性高点位置取大", "量价", 44, 101, _ALL,
             "max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume), 3.83878), 4.16783), 8.38151), "
             "Ts_Rank(decay_linear(Ts_ArgMax(correlation(Ts_Rank(close, 7.45404), Ts_Rank(adv60, 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1" + _SPARSE_NOTE, _alpha096),
    _Formula(98, "均价成交额相关性与开盘成交额相关性低点位置之差", "量价", 38, 53, ("raw_open", "raw_high", "raw_low", "volume", "amount"),
             "rank(decay_linear(correlation(vwap, sum(adv5, 26.4719), 4.58418), 7.18088)) "
             "- rank(decay_linear(Ts_Rank(Ts_ArgMin(correlation(rank(open), rank(adv15), 20.8187), 8.62571), 6.95668), 8.07206))", _alpha098),
    _Formula(99, "中间价与成交额相关性和低价成交量相关性比较", "量价", 25, 85, ("raw_high", "raw_low", "volume", "amount"),
             "(rank(correlation(sum((high + low) / 2, 19.8975), sum(adv60, 19.8975), 8.8136)) < rank(correlation(low, volume, 6.28259))) * -1", _alpha099),
)

_IND = ("industry", "sector")
_IND_NOTE = "（sector 用证监会门类，industry、subindustry 都用大类；当天同大类不到 5 只股票时和整个门类比较，门类也不到 5 只就没有值）"
_PRICE = ("raw_high", "raw_low", "raw_close", "volume", "amount")

_THIRD_BATCH: tuple[_Formula, ...] = (
    _Formula(48, "价格变化的持续性（行业内比较）", "动量", 0, 252, ("raw_close", *_IND),
             "indneutralize((correlation(delta(close, 1), delta(delay(close, 1), 1), 250) * delta(close, 1)) / close, IndClass.subindustry) "
             "/ sum((delta(close, 1) / delay(close, 1))^2, 250)" + _IND_NOTE + _LONG_NOTE, _alpha048),
    _Formula(58, "均价（门类内比较）与成交量的相关性", "量价", 12, 13, (*_V, *_IND),
             "-Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.sector), volume, 3.92795), 7.89291), 5.50322)" + _IND_NOTE, _alpha058),
    _Formula(59, "均价（大类内比较）与成交量的相关性", "量价", 25, 26, (*_V, *_IND),
             "-Ts_Rank(decay_linear(correlation(IndNeutralize(vwap * 0.728317 + vwap * (1 - 0.728317), IndClass.industry), volume, 4.25197), 16.2289), 8.19648)"
             + _IND_NOTE, _alpha059),
    _Formula(63, "收盘价变化（大类内比较）减均价与长期成交额的相关性", "量价", 23, 239, (*_ALL, *_IND),
             "(rank(decay_linear(delta(IndNeutralize(close, IndClass.industry), 2.25164), 8.22237)) "
             "- rank(decay_linear(correlation(vwap * 0.318108 + open * (1 - 0.318108), sum(adv180, 37.2467), 13.557), 12.2883))) * -1" + _IND_NOTE, _alpha063),
    _Formula(67, "最高价离低点的位置，以行业内量价相关性为次方", "量价", 5, 25, (*_V, *_IND),
             "(rank(high - ts_min(high, 2.14593))^rank(correlation(IndNeutralize(vwap, IndClass.sector), IndNeutralize(adv20, IndClass.subindustry), 6.02936))) * -1"
             + _IND_NOTE, _alpha067),
    _Formula(69, "均价变化高点（大类内比较），以收盘均价与成交额相关性为次方", "量价", 11, 31, (*_PRICE, *_IND),
             "(rank(ts_max(delta(IndNeutralize(vwap, IndClass.industry), 2.72412), 4.79344))"
             "^Ts_Rank(correlation(close * 0.490655 + vwap * (1 - 0.490655), adv20, 4.92416), 9.0615)) * -1" + _IND_NOTE, _alpha069),
    _Formula(70, "均价变化，以收盘价（大类内比较）与成交额相关性为次方", "量价", 32, 82, (*_PRICE, *_IND),
             "(rank(delta(vwap, 1.29456))^Ts_Rank(correlation(IndNeutralize(close, IndClass.industry), adv50, 17.8256), 17.9171)) * -1" + _IND_NOTE, _alpha070),
    _Formula(76, "均价变化与最低价（门类内比较）成交额相关性取大", "量价", 59, 140, (*_V, *_IND),
             "max(rank(decay_linear(delta(vwap, 1.24383), 11.8259)), "
             "Ts_Rank(decay_linear(Ts_Rank(correlation(IndNeutralize(low, IndClass.sector), adv81, 8.14941), 19.569), 17.1543), 19.383)) * -1" + _IND_NOTE, _alpha076),
    _Formula(79, "收盘开盘价变化（门类内比较）和均价与成交额时序相关性比较", "量价", 15, 171, (*_ALL, *_IND),
             "rank(delta(IndNeutralize(close * 0.60733 + open * (1 - 0.60733), IndClass.sector), 1.23438)) "
             "< rank(correlation(Ts_Rank(vwap, 3.60973), Ts_Rank(adv150, 9.18637), 14.6644))" + _IND_NOTE, _alpha079),
    _Formula(80, "开盘最高价变化方向（大类内比较），以最高价与成交额相关性为次方", "量价", 8, 18, ("raw_open", "raw_high", "amount", *_IND),
             "(rank(Sign(delta(IndNeutralize(open * 0.868128 + high * (1 - 0.868128), IndClass.industry), 4.04545)))"
             "^Ts_Rank(correlation(high, adv10, 5.11456), 5.53756)) * -1" + _IND_NOTE, _alpha080),
    _Formula(82, "开盘价变化与成交量（门类内比较）开盘价相关性取小", "量价", 33, 34, ("raw_open", "volume", *_IND),
             "min(rank(decay_linear(delta(open, 1.46063), 14.8717)), "
             "Ts_Rank(decay_linear(correlation(IndNeutralize(volume, IndClass.sector), open * 0.634196 + open * (1 - 0.634196), 17.4842), 6.92131), 13.4283)) * -1"
             + _IND_NOTE, _alpha082),
    _Formula(87, "收盘均价变化与成交额（大类内比较）收盘价相关性取大", "量价", 28, 109, (*_PRICE, *_IND),
             "max(rank(decay_linear(delta(close * 0.369701 + vwap * (1 - 0.369701), 1.91233), 2.65461)), "
             "Ts_Rank(decay_linear(abs(correlation(IndNeutralize(adv81, IndClass.industry), close, 13.4132)), 4.89768), 14.4535)) * -1" + _IND_NOTE, _alpha087),
    _Formula(89, "最低价与成交额相关性减均价变化（大类内比较）", "量价", 26, 27, (*_V, *_IND),
             "Ts_Rank(decay_linear(correlation(low * 0.967285 + low * (1 - 0.967285), adv10, 6.94279), 5.51607), 3.79744) "
             "- Ts_Rank(decay_linear(delta(IndNeutralize(vwap, IndClass.industry), 3.48158), 10.1466), 15.3012)" + _IND_NOTE, _alpha089),
    _Formula(90, "收盘价离高点的位置，以成交额（行业内比较）与最低价相关性为次方", "量价", 6, 46, ("raw_low", "raw_close", "amount", *_IND),
             "(rank(close - ts_max(close, 4.66719))^Ts_Rank(correlation(IndNeutralize(adv40, IndClass.subindustry), low, 5.38375), 3.21856)) * -1"
             + _IND_NOTE, _alpha090),
    _Formula(91, "收盘价（大类内比较）与成交量相关性减均价与成交额相关性", "量价", 28, 34, (*_PRICE, *_IND),
             "(Ts_Rank(decay_linear(decay_linear(correlation(IndNeutralize(close, IndClass.industry), volume, 9.74928), 16.398), 3.83219), 4.8667) "
             "- rank(decay_linear(correlation(vwap, adv30, 4.01303), 2.6809))) * -1" + _IND_NOTE, _alpha091),
    _Formula(93, "均价（大类内比较）与成交额相关性比收盘均价变化", "量价", 40, 121, (*_PRICE, *_IND),
             "Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.industry), adv81, 17.4193), 19.848), 7.54455) "
             "/ rank(decay_linear(delta(close * 0.524434 + vwap * (1 - 0.524434), 2.77377), 16.2664))" + _IND_NOTE, _alpha093),
    _Formula(97, "低价均价变化（大类内比较）减最低价与成交额的时序相关性", "量价", 45, 115, (*_V, *_IND),
             "(rank(decay_linear(delta(IndNeutralize(low * 0.721001 + vwap * (1 - 0.721001), IndClass.industry), 3.3705), 20.4523)) "
             "- Ts_Rank(decay_linear(Ts_Rank(correlation(Ts_Rank(low, 7.87871), Ts_Rank(adv60, 17.255), 4.97547), 18.5925), 15.7152), 6.71659)) * -1"
             + _IND_NOTE + _SPARSE_NOTE_97, _alpha097),
    _Formula(100, "日内买卖力量与趋势（行业内比较）乘相对成交额", "量价", 29, 30, (*_PRICE, *_IND),
             "-((1.5 * scale(indneutralize(indneutralize(rank(((close - low) - (high - close)) / (high - low) * volume), IndClass.subindustry), IndClass.subindustry)) "
             "- scale(indneutralize(correlation(close, rank(adv20), 5) - rank(ts_argmin(close, 30)), IndClass.subindustry))) * (volume / adv20))"
             + _IND_NOTE + _AMOUNT_NOTE, _alpha100),
)

FORMULAS = tuple(sorted(FORMULAS + _SECOND_BATCH + _THIRD_BATCH, key=lambda item: item.number))
# 有复权因子时每个公式都会用到：识别除权除息日、计算真实收益、按当天的前复权价计算长窗口。
_ADJUSTMENT = ("adj_factor", "adjusted_close", UNIVERSE_COLUMN)


def alpha101_factors() -> list[FactorDefinition]:
    return [
        BuiltinFactor(
            name=f"alpha101_{item.number:03d}",
            display_name=item.title,
            description=f"{item.title}。按原公式计算，正向输出；A股有效性需独立评估。",
            formula=item.formula,
            required_fields=item.fields,
            optional_fields=_ADJUSTMENT,
            min_history=item.history,
            category=item.category,
            source="Alpha101",
            source_url="https://arxiv.org/abs/1601.00991",
            func=item.compute,
        )
        for item in FORMULAS
    ]
