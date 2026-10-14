"""A verified subset of the 101 Formulaic Alphas, computed from daily bars.

Source: https://arxiv.org/abs/1601.00991 (Appendix A). Each formula below is the paper's,
with the paper's operator definitions. 82 of the 101 need only daily price and volume; the
other 19 need an industry classification (18) or market cap (#56), which the local data lacks.

Conventions, chosen so that no value depends on data after its own date:

- Prices and volume are the raw ones of each day. No adjusted price stands in for them, so
  price levels and same-day comparisons are the ones traders saw.
- ``returns`` is the true close-to-close return (from the adjusted close), so an ex-dividend
  day is not counted as a loss.
- ``vwap`` is amount / volume of the day; ``adv{d}`` is the average amount over ``d`` days,
  as the paper defines it. Formulas that compare ``adv`` with share volume are left out.
- A dividend or split makes raw prices and volumes before and after it incomparable. A value
  whose price/volume window spans such a day is left missing rather than computed from a
  jump that never traded (``span`` below is the number of day-to-day steps the window covers).
  Other stocks' cross-sectional ranks on that day still count the affected stock.
- ``rank`` is the cross-sectional average percentile rank within the supplied universe; when
  the bars carry an ``in_universe`` mark (an index's members on each day), only that day's
  members are ranked;
  ``ts_rank`` the same within a stock's own window. Undefined results stay missing.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_platform.data.index_constituents import UNIVERSE_COLUMN
from quant_platform.factors.base import FactorDefinition, melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor

# 复权因子相邻两天的变化超过这个比例，就认为这一天发生了除权除息。
ACTION_THRESHOLD = 1e-3

Frame = pd.DataFrame


# --------------------------------------------------------------------------- #
# Operators (paper, Appendix A.1). Frames are date x symbol.
# --------------------------------------------------------------------------- #


# 研究范围是指数当时的成分股时，截面排名只在当天的成分股之间进行（日期 x 股票的布尔表）。
_UNIVERSE: ContextVar[Frame | None] = ContextVar("alpha101_universe", default=None)


def rank(x: Frame) -> Frame:
    members = _UNIVERSE.get()
    if members is not None:
        x = x.where(members.reindex(index=x.index, columns=x.columns, fill_value=False))
    return x.rank(axis=1, pct=True)


def delay(x: Frame, d: int) -> Frame:
    return x.shift(d)


def delta(x: Frame, d: int) -> Frame:
    return x.diff(d)


def ts_sum(x: Frame, d: int) -> Frame:
    return x.rolling(d, min_periods=d).sum()


def ts_min(x: Frame, d: int) -> Frame:
    return x.rolling(d, min_periods=d).min()


def ts_max(x: Frame, d: int) -> Frame:
    return x.rolling(d, min_periods=d).max()


def ts_rank(x: Frame, d: int) -> Frame:
    return x.rolling(d, min_periods=d).rank(pct=True)


def stddev(x: Frame, d: int) -> Frame:
    return x.rolling(d, min_periods=d).std()


# 相关系数和协方差保留的小数位。滚动计算会留下 1e-16 量级的舍入误差；不去掉的话，
# 数学上相等的两个值会在之后的 rank 里被排出先后。
MOMENT_DECIMALS = 12


def _flat(x: Frame, d: int) -> Frame:
    """Windows in which the series did not move: their covariance is exactly zero and their
    correlation undefined, whatever rounding noise the rolling computation leaves."""

    return ts_max(x, d) == ts_min(x, d)


def correlation(x: Frame, y: Frame, d: int) -> Frame:
    result = x.rolling(d, min_periods=d).corr(y).replace([np.inf, -np.inf], np.nan)
    return result.where(~(_flat(x, d) | _flat(y, d))).round(MOMENT_DECIMALS)


def covariance(x: Frame, y: Frame, d: int) -> Frame:
    result = x.rolling(d, min_periods=d).cov(y)
    return result.where(~(_flat(x, d) | _flat(y, d)) | result.isna(), 0.0).round(MOMENT_DECIMALS)


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


def alpha101_factors() -> list[FactorDefinition]:
    return [
        BuiltinFactor(
            name=f"alpha101_{item.number:03d}",
            display_name=item.title,
            description=f"{item.title}。按原公式计算，正向输出；A股有效性需独立评估。",
            formula=item.formula,
            required_fields=item.fields,
            min_history=item.history,
            category=item.category,
            source="Alpha101",
            source_url="https://arxiv.org/abs/1601.00991",
            func=item.compute,
        )
        for item in FORMULAS
    ]
