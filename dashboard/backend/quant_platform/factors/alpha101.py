"""First verified Alpha101 subset; original formulas with raw OHLC and volume.

Source: https://arxiv.org/abs/1601.00991 (Appendix A).
No silent substitution of adjusted close for raw OHLC. Corporate actions can
affect these raw-price signals. Cross-sectional ranks use average percentile
ranks within the supplied universe; undefined correlations remain missing.
"""

import numpy as np
import pandas as pd

from quant_platform.factors.base import FactorDefinition, melt_wide, pivot_field
from quant_platform.factors.builtins import BuiltinFactor


def _alpha006(bars: pd.DataFrame) -> pd.DataFrame:
    opening = pivot_field(bars, "raw_open")
    volume = pivot_field(bars, "volume")
    result = opening.rolling(10, min_periods=10).corr(volume)
    return melt_wide(-result.replace([np.inf, -np.inf], np.nan))


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
            6,
            "开盘价与成交量相关性",
            "量价",
            10,
            ("raw_open", "volume"),
            "-correlation(open, volume, 10)",
            _alpha006,
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
            33,
            "开收盘比例截面排名",
            "反转",
            1,
            ("raw_open", "raw_close"),
            "rank(open / close - 1)",
            _alpha033,
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
            description=f"{title}。按原公式计算，正向输出；A股有效性需独立评估。",
            formula=formula,
            required_fields=fields,
            min_history=history,
            category=category,
            source="Alpha101",
            source_url="https://arxiv.org/abs/1601.00991",
            func=func,
        )
        for number, title, category, history, fields, formula, func in definitions
    ]
