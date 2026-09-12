"""First 20 Alpha101 price-volume factors, using raw OHLC and volume.

Source: https://arxiv.org/abs/1601.00991 (Appendix A).
No silent substitution of adjusted close for raw OHLC. Corporate actions can
affect these raw-price signals. Cross-sectional ranks use average percentile
ranks within the supplied universe; undefined correlations remain missing.
"""

import numpy as np
import pandas as pd

from quant_platform.factors.alpha_operators import choose, correlation, divide, finite, rank
from quant_platform.factors.base import FactorDefinition, melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor


def _price(bars, field):
    return finite(pivot_field(bars, field))


def _returns(bars):
    close = _price(bars, "raw_close")
    return divide(close, close.shift(1)) - 1


def _alpha002(bars):
    volume = _price(bars, "volume")
    volume_change = np.log(volume.where(volume > 0)).diff(2)
    opening = _price(bars, "raw_open")
    intraday = divide(_price(bars, "raw_close") - opening, opening)
    return melt_wide(-correlation(rank(volume_change), rank(intraday), 6))


def _alpha003(bars):
    return melt_wide(-correlation(rank(_price(bars, "raw_open")), rank(_price(bars, "volume")), 10))


def _conditional_change(bars, window):
    change = _price(bars, "raw_close").diff()
    low = change.rolling(window).min()
    high = change.rolling(window).max()
    return choose((low > 0) | (high < 0), change, -change, valid=low.notna() & high.notna())


def _alpha009(bars):
    return melt_wide(_conditional_change(bars, 5))


def _alpha010(bars):
    return melt_wide(rank(_conditional_change(bars, 4)))


def _rank_covariance(bars, field):
    return -rank(rank(_price(bars, field)).rolling(5).cov(rank(_price(bars, "volume"))))


def _alpha013(bars):
    return melt_wide(_rank_covariance(bars, "raw_close"))


def _alpha014(bars):
    return melt_wide(
        -rank(_returns(bars).diff(3))
        * correlation(_price(bars, "raw_open"), _price(bars, "volume"), 10)
    )


def _alpha015(bars):
    corr = correlation(rank(_price(bars, "raw_high")), rank(_price(bars, "volume")), 3)
    return melt_wide(-rank(corr).rolling(3).sum())


def _alpha016(bars):
    return melt_wide(_rank_covariance(bars, "raw_high"))


def _alpha018(bars):
    close, opening = _price(bars, "raw_close"), _price(bars, "raw_open")
    spread = close - opening
    return melt_wide(
        -rank(spread.abs().rolling(5).std() + spread + correlation(close, opening, 10))
    )


def _alpha020(bars):
    opening = _price(bars, "raw_open")
    return melt_wide(
        -rank(opening - _price(bars, "raw_high").shift(1))
        * rank(opening - _price(bars, "raw_close").shift(1))
        * rank(opening - _price(bars, "raw_low").shift(1))
    )


def _alpha022(bars):
    corr = correlation(_price(bars, "raw_high"), _price(bars, "volume"), 5)
    return melt_wide(-corr.diff(5) * rank(_price(bars, "raw_close").rolling(20).std()))


def _alpha023(bars):
    high = _price(bars, "raw_high")
    mean = high.rolling(20).mean()
    change = high.diff(2)
    return melt_wide(choose(mean < high, -change, 0.0, valid=mean.notna() & change.notna()))


def _alpha034(bars):
    returns = _returns(bars)
    volatility_ratio = divide(returns.rolling(2).std(), returns.rolling(5).std())
    return melt_wide(rank(2 - rank(volatility_ratio) - rank(_price(bars, "raw_close").diff())))


def _alpha040(bars):
    high = _price(bars, "raw_high")
    return melt_wide(-rank(high.rolling(10).std()) * correlation(high, _price(bars, "volume"), 10))


def _alpha044(bars):
    return melt_wide(-correlation(_price(bars, "raw_high"), rank(_price(bars, "volume")), 5))


def _alpha055(bars):
    low = _price(bars, "raw_low").rolling(12).min()
    high = _price(bars, "raw_high").rolling(12).max()
    location = divide(_price(bars, "raw_close") - low, high - low)
    return melt_wide(-correlation(rank(location), rank(_price(bars, "volume")), 6))


def _alpha006(bars: pd.DataFrame) -> pd.DataFrame:
    opening = pivot_field(bars, "raw_open")
    volume = pivot_field(bars, "volume")
    return melt_wide(-correlation(opening, volume, 10))


def _alpha012(bars: pd.DataFrame) -> pd.DataFrame:
    return melt_wide(
        -np.sign(pivot_field(bars, "volume").diff()) * pivot_field(bars, "raw_close").diff()
    )


def _alpha033(bars: pd.DataFrame) -> pd.DataFrame:
    close = pivot_field(bars, "raw_close").replace(0, np.nan)
    return melt_wide((pivot_field(bars, "raw_open") / close - 1).rank(axis=1, pct=True))


def _alpha101(bars: pd.DataFrame) -> pd.DataFrame:
    return melt_wide(
        (pivot_field(bars, "raw_close") - pivot_field(bars, "raw_open"))
        / (pivot_field(bars, "raw_high") - pivot_field(bars, "raw_low") + 0.001)
    )


def alpha101_factors() -> list[FactorDefinition]:
    definitions = [
        (
            2,
            "成交量变化与日内涨跌相关性",
            "量价",
            8,
            ("raw_open", "raw_close", "volume"),
            "-correlation(rank(delta(log(volume), 2)), rank((close - open) / open), 6)",
            _alpha002,
        ),
        (
            3,
            "开盘价排名与成交量排名相关性",
            "量价",
            10,
            ("raw_open", "volume"),
            "-correlation(rank(open), rank(volume), 10)",
            _alpha003,
        ),
        (
            6,
            "开盘价与成交量相关性",
            "量价",
            10,
            ("raw_open", "volume"),
            "-correlation(open, volume, 10)",
            _alpha006,
        ),
        (
            9,
            "连续涨跌条件下的价格变化",
            "反转",
            6,
            ("raw_close",),
            "ts_min(delta(close, 1), 5) > 0 ? delta(close, 1) : "
            "(ts_max(delta(close, 1), 5) < 0 ? delta(close, 1) : -delta(close, 1))",
            _alpha009,
        ),
        (
            10,
            "连续涨跌条件价格变化排名",
            "反转",
            5,
            ("raw_close",),
            "rank(ts_min(delta(close, 1), 4) > 0 ? delta(close, 1) : "
            "(ts_max(delta(close, 1), 4) < 0 ? delta(close, 1) : -delta(close, 1)))",
            _alpha010,
        ),
        (
            12,
            "量变方向与价格变化",
            "量价",
            2,
            ("raw_close", "volume"),
            "sign(delta(volume, 1)) * -delta(close, 1)",
            _alpha012,
        ),
        (
            13,
            "收盘价与成交量排名协方差",
            "量价",
            5,
            ("raw_close", "volume"),
            "-rank(covariance(rank(close), rank(volume), 5))",
            _alpha013,
        ),
        (
            14,
            "收益变化与开盘量价相关性",
            "量价",
            10,
            ("raw_open", "raw_close", "volume"),
            "-rank(delta(returns, 3)) * correlation(open, volume, 10)",
            _alpha014,
        ),
        (
            15,
            "高价与成交量排名相关性累积",
            "量价",
            5,
            ("raw_high", "volume"),
            "-sum(rank(correlation(rank(high), rank(volume), 3)), 3)",
            _alpha015,
        ),
        (
            16,
            "最高价与成交量排名协方差",
            "量价",
            5,
            ("raw_high", "volume"),
            "-rank(covariance(rank(high), rank(volume), 5))",
            _alpha016,
        ),
        (
            18,
            "日内价差波动与开收盘相关性",
            "K线",
            10,
            ("raw_open", "raw_close"),
            "-rank(stddev(abs(close - open), 5) + close - open + correlation(close, open, 10))",
            _alpha018,
        ),
        (
            20,
            "开盘价相对昨日价格位置",
            "反转",
            2,
            ("raw_open", "raw_high", "raw_low", "raw_close"),
            "-rank(open - delay(high, 1)) * rank(open - delay(close, 1)) * "
            "rank(open - delay(low, 1))",
            _alpha020,
        ),
        (
            22,
            "高价量价相关变化与收盘波动",
            "量价",
            20,
            ("raw_high", "raw_close", "volume"),
            "-delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))",
            _alpha022,
        ),
        (
            23,
            "高价突破均值后的反向变化",
            "反转",
            20,
            ("raw_high",),
            "sum(high, 20) / 20 < high ? -delta(high, 2) : 0",
            _alpha023,
        ),
        (
            33,
            "开收盘比例截面排名",
            "反转",
            1,
            ("raw_open", "raw_close"),
            "rank(open / close - 1)",
            _alpha033,
        ),
        (
            34,
            "收益波动比与价格反转排名",
            "反转",
            6,
            ("raw_close",),
            "rank(1 - rank(stddev(returns, 2) / stddev(returns, 5)) + 1 - rank(delta(close, 1)))",
            _alpha034,
        ),
        (
            40,
            "最高价波动与成交量相关性",
            "量价",
            10,
            ("raw_high", "volume"),
            "-rank(stddev(high, 10)) * correlation(high, volume, 10)",
            _alpha040,
        ),
        (
            44,
            "最高价与成交量排名相关性",
            "量价",
            5,
            ("raw_high", "volume"),
            "-correlation(high, rank(volume), 5)",
            _alpha044,
        ),
        (
            55,
            "区间价格位置与成交量排名相关性",
            "量价",
            17,
            ("raw_close", "raw_high", "raw_low", "volume"),
            "-correlation(rank((close - ts_min(low, 12)) / "
            "(ts_max(high, 12) - ts_min(low, 12))), rank(volume), 6)",
            _alpha055,
        ),
        (
            101,
            "K线实体占振幅比例",
            "K线",
            1,
            ("raw_open", "raw_close", "raw_high", "raw_low"),
            "(close - open) / (high - low + 0.001)",
            _alpha101,
        ),
    ]
    return [
        BuiltinFactor(
            name=f"alpha101_{number:03d}",
            display_name=title,
            description=f"{title}。按公式符号输出；缺失或预热不足不填零，A股有效性需独立评估。",
            formula=formula,
            required_fields=fields,
            min_history=history,
            category=category,
            source="Alpha101",
            source_url="https://arxiv.org/abs/1601.00991",
            version="1.0.1" if number == 6 else "1.0.0",
            func=func,
        )
        for number, title, category, history, fields, formula, func in definitions
    ]
