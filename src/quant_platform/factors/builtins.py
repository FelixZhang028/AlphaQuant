"""内置因子库：仅依赖 daily_bars 已有字段的 10 个经典量价因子。

可用字段（见 ``data/normalizers.CANONICAL_BAR_COLUMNS`` 与复权拼接逻辑）：
``raw_open/raw_high/raw_low/raw_close/pre_close/volume/amount/adjusted_close``。
当前数据源没有换手率（turnover）字段，因此量比类因子用成交量构造。

所有实现均为因果算子（rolling / shift / expanding），保证无未来函数。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from quant_platform.factors.base import (
    FACTOR_COLUMNS,
    FactorDefinition,
    melt_wide,
    pivot_field,
)

_PRICE = "adjusted_close"


def _close(bars: pd.DataFrame) -> pd.DataFrame:
    """前复权收盘价宽表；缺失 adjusted_close 时退化为 raw_close。"""

    if _PRICE in bars.columns and bars[_PRICE].notna().any():
        return pivot_field(bars, _PRICE)
    return pivot_field(bars, "raw_close")


def _momentum_20(bars: pd.DataFrame) -> pd.DataFrame:
    close = _close(bars)
    return melt_wide(close / close.shift(20) - 1.0)


def _reversal_5(bars: pd.DataFrame) -> pd.DataFrame:
    close = _close(bars)
    return melt_wide(close / close.shift(5) - 1.0)


def _volatility_20(bars: pd.DataFrame) -> pd.DataFrame:
    returns = _close(bars).pct_change()
    return melt_wide(returns.rolling(20, min_periods=20).std())


def _amount_change_20(bars: pd.DataFrame) -> pd.DataFrame:
    amount = pivot_field(bars, "amount")
    recent = amount.rolling(5, min_periods=5).mean()
    baseline = amount.rolling(20, min_periods=20).mean()
    return melt_wide(recent / baseline - 1.0)


def _rsi_14(bars: pd.DataFrame) -> pd.DataFrame:
    diff = _close(bars).diff()
    gain = diff.clip(lower=0.0)
    loss = -diff.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / 14, min_periods=14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - 100.0 / (1.0 + rs)
    rsi = rsi.where(avg_loss != 0.0, 100.0)
    return melt_wide(rsi)


def _high_distance_20(bars: pd.DataFrame) -> pd.DataFrame:
    # 分子、分母必须使用同一价格口径；复权收盘价不能与未复权最高价混用。
    close = pivot_field(bars, "raw_close")
    high = pivot_field(bars, "raw_high")
    rolling_high = high.rolling(20, min_periods=20).max()
    return melt_wide(close / rolling_high - 1.0)


def _volume_ratio_5(bars: pd.DataFrame) -> pd.DataFrame:
    volume = pivot_field(bars, "volume")
    recent = volume.rolling(5, min_periods=5).mean()
    baseline = volume.rolling(20, min_periods=20).mean()
    return melt_wide(recent / baseline)


def _pv_corr_20(bars: pd.DataFrame) -> pd.DataFrame:
    close = _close(bars)
    volume = pivot_field(bars, "volume")
    result: dict[str, pd.Series] = {}
    for symbol in close.columns:
        if symbol not in volume.columns:
            continue
        result[symbol] = close[symbol].rolling(20, min_periods=20).corr(volume[symbol])
    if not result:
        return pd.DataFrame(columns=FACTOR_COLUMNS)
    return melt_wide(pd.DataFrame(result))


def _bias_10(bars: pd.DataFrame) -> pd.DataFrame:
    close = _close(bars)
    ma10 = close.rolling(10, min_periods=10).mean()
    return melt_wide(close / ma10 - 1.0)


def _amplitude_20(bars: pd.DataFrame) -> pd.DataFrame:
    high = pivot_field(bars, "raw_high")
    low = pivot_field(bars, "raw_low")
    pre_close = (
        pivot_field(bars, "pre_close") if "pre_close" in bars.columns else _close(bars).shift(1)
    )
    amplitude = (high - low) / pre_close.replace(0.0, np.nan)
    return melt_wide(amplitude.rolling(20, min_periods=20).mean())


@dataclass(frozen=True)
class BuiltinFactor(FactorDefinition):
    """由计算函数参数化的内置因子。"""

    func: Callable[[pd.DataFrame], pd.DataFrame] = field(
        default=lambda bars: pd.DataFrame(columns=FACTOR_COLUMNS), repr=False
    )

    def compute(self, bars: pd.DataFrame) -> pd.DataFrame:
        missing = [f for f in self.required_fields if f not in bars.columns]
        if missing:
            raise ValueError(f"因子 {self.name} 缺少字段: {missing}")
        result = self.func(bars)
        return result[FACTOR_COLUMNS].reset_index(drop=True)


def builtin_factors() -> list[FactorDefinition]:
    """返回全部内置因子定义。"""

    return [
        BuiltinFactor(
            name="momentum_20",
            display_name="20日动量",
            description="过去 20 个交易日的累计涨跌幅，捕捉中期趋势延续效应。",
            formula="adjusted_close(t) / adjusted_close(t-20) - 1",
            required_fields=(_PRICE,),
            min_history=21,
            direction=1,
            category="动量",
            func=_momentum_20,
        ),
        BuiltinFactor(
            name="reversal_5",
            display_name="5日反转",
            description="过去 5 日涨跌幅的反转因子：短期跌得越多，预期反弹越强。",
            formula="adjusted_close(t) / adjusted_close(t-5) - 1（反向使用）",
            required_fields=(_PRICE,),
            min_history=6,
            direction=-1,
            category="反转",
            func=_reversal_5,
        ),
        BuiltinFactor(
            name="volatility_20",
            display_name="20日波动率",
            description="过去 20 日日收益率标准差，低波动股票风险调整后收益通常更优。",
            formula="std(daily_return, 20)",
            required_fields=(_PRICE,),
            min_history=21,
            direction=-1,
            category="波动",
            func=_volatility_20,
        ),
        BuiltinFactor(
            name="amount_change_20",
            display_name="20日成交额变化率",
            description="近 5 日平均成交额相对近 20 日平均成交额的变化率，刻画资金关注度提升。",
            formula="mean(amount, 5) / mean(amount, 20) - 1",
            required_fields=("amount",),
            min_history=20,
            direction=1,
            category="量价",
            func=_amount_change_20,
        ),
        BuiltinFactor(
            name="rsi_14",
            display_name="RSI14",
            description="14 日相对强弱指标，数值越高代表短期超买，反向使用。",
            formula="RSI = 100 - 100 / (1 + 14日平均涨幅 / 14日平均跌幅)（Wilder 平滑）",
            required_fields=(_PRICE,),
            min_history=15,
            direction=-1,
            category="反转",
            func=_rsi_14,
        ),
        BuiltinFactor(
            name="high_distance_20",
            display_name="20日新高距离",
            description="收盘价相对过去 20 日最高价的距离，越接近新高（值越接近 0）突破动能越强。",
            formula="raw_close(t) / max(raw_high, 20) - 1",
            required_fields=("raw_close", "raw_high"),
            min_history=20,
            direction=1,
            category="动量",
            func=_high_distance_20,
        ),
        BuiltinFactor(
            name="volume_ratio_5",
            display_name="5日量比",
            description="近 5 日平均成交量与近 20 日平均成交量之比，衡量短期放量程度。",
            formula="mean(volume, 5) / mean(volume, 20)",
            required_fields=("volume",),
            min_history=20,
            direction=1,
            category="量价",
            func=_volume_ratio_5,
        ),
        BuiltinFactor(
            name="pv_corr_20",
            display_name="20日量价相关性",
            description="过去 20 日收盘价与成交量的相关系数，量价背离（负相关）常预示反转。",
            formula="corr(adjusted_close, volume, 20)（反向使用）",
            required_fields=(_PRICE, "volume"),
            min_history=20,
            direction=-1,
            category="量价",
            func=_pv_corr_20,
        ),
        BuiltinFactor(
            name="bias_10",
            display_name="10日乖离率",
            description="收盘价偏离 10 日均线的幅度，偏离越大回归压力越大，反向使用。",
            formula="adjusted_close(t) / ma(adjusted_close, 10) - 1（反向使用）",
            required_fields=(_PRICE,),
            min_history=10,
            direction=-1,
            category="反转",
            func=_bias_10,
        ),
        BuiltinFactor(
            name="amplitude_20",
            display_name="20日振幅",
            description="过去 20 日（最高-最低）/昨收 的均值，低振幅股票走势更稳健。",
            formula="mean((raw_high - raw_low) / pre_close, 20)（反向使用）",
            required_fields=("raw_high", "raw_low", "pre_close"),
            min_history=21,
            direction=-1,
            category="波动",
            func=_amplitude_20,
        ),
    ]
