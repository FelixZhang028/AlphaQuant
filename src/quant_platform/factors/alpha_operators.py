"""Shared Alpha101 operators; full windows and missing values are preserved."""

from math import floor

import numpy as np
import pandas as pd


def window_days(value):
    """The paper floors fractional lookbacks; reject nonpositive windows."""
    result = floor(value)
    if result < 1:
        raise ValueError("滚动窗口向下取整后必须至少为 1")
    return result


def ts_rank(value, window):
    """Last observation's average ordinal rank (1..d), not percentile rank."""

    def last_rank(x):
        x = np.round(x / (np.max(np.abs(x)) or 1.0), 12)
        return float(np.sum(x < x[-1]) + (np.sum(x == x[-1]) + 1) / 2)

    return finite(value).rolling(window_days(window)).apply(last_rank, raw=True)


def decay_linear(value, window):
    """Oldest weight 1, newest weight d; never fill incomplete windows."""
    days = window_days(window)
    weights = np.arange(1, days + 1, dtype=float)
    weights /= weights.sum()
    return finite(value).rolling(days).apply(lambda x: np.dot(x, weights), raw=True)


def ts_argmax(value, window):
    """Oldest=1, newest=d; equal maxima use the earliest position."""
    return (
        finite(value)
        .rolling(window_days(window))
        .apply(lambda x: np.argmax(np.round(x / (np.max(np.abs(x)) or 1.0), 12)) + 1, raw=True)
    )


def ts_argmin(value, window):
    """Oldest=1, newest=d; equal minima use the earliest position."""
    return (
        finite(value)
        .rolling(window_days(window))
        .apply(lambda x: np.argmin(np.round(x / (np.max(np.abs(x)) or 1.0), 12)) + 1, raw=True)
    )


def finite(value: pd.DataFrame) -> pd.DataFrame:
    return value.replace([np.inf, -np.inf], np.nan)


def rank(value: pd.DataFrame) -> pd.DataFrame:
    """Average percentile rank, with relative 1e-12 precision for numerical ties."""
    value = finite(value)
    scale = value.abs().max(axis=1).replace(0, 1.0)
    normalized = value.div(scale, axis=0).round(12)
    return normalized.rank(axis=1, method="average", pct=True)


def divide(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    return finite(left / right.replace(0, np.nan))


def correlation(left: pd.DataFrame, right: pd.DataFrame, window: int) -> pd.DataFrame:
    left, right = finite(left), finite(right)
    x, y = left.rolling(window), right.rolling(window)
    if window == 2:
        # Two distinct observations have exact correlation +/-1. Avoid unstable
        # rolling-moment cancellation changing a later cross-sectional rank.
        dx, dy = left.diff(), right.diff()
        return (np.sign(dx) * np.sign(dy)).where(dx.ne(0) & dy.ne(0))
    result = x.corr(right)
    # pandas may produce spurious finite values for constant floating-point windows.
    valid = (x.max() > x.min()) & (y.max() > y.min())
    return finite(result).where(valid).clip(-1.0, 1.0)


def choose(condition, yes, no, *, valid):
    """Unlike NaN comparisons, an unavailable condition must not select a branch."""
    return yes.where(condition, no).where(valid)
