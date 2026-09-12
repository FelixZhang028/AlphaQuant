"""Shared Alpha101 operators; full windows and missing values are preserved."""

import numpy as np
import pandas as pd


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
    result = x.corr(right)
    # pandas may produce spurious finite values for constant floating-point windows.
    valid = (x.max() > x.min()) & (y.max() > y.min())
    return finite(result).where(valid).clip(-1.0, 1.0)


def choose(condition, yes, no, *, valid):
    """Unlike NaN comparisons, an unavailable condition must not select a branch."""
    return yes.where(condition, no).where(valid)
