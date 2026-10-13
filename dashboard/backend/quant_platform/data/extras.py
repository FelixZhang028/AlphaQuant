"""Data a factor or strategy can ask for beyond the daily bar itself.

Two kinds, each in its own table: daily valuation and turnover indicators, and quarterly
financial reports joined point in time. Callers name the columns they need; nothing extra is
read otherwise.
"""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from quant_platform.data.fundamentals import MISSING_FUNDAMENTALS_MESSAGE, fundamental_columns
from quant_platform.data.indicators import MISSING_INDICATORS_MESSAGE, indicator_columns


def extra_columns(fields: Iterable[str]) -> list[str]:
    """The indicator and financial-report columns among ``fields``."""

    wanted = list(fields)
    return [*indicator_columns(wanted), *fundamental_columns(wanted)]


def require_extra_data(bars: pd.DataFrame, columns: Iterable[str]) -> None:
    """Fail with a message the user can act on when a requested column was never downloaded."""

    wanted = list(columns)
    for names, message in ((indicator_columns(wanted), MISSING_INDICATORS_MESSAGE),
                           (fundamental_columns(wanted), MISSING_FUNDAMENTALS_MESSAGE)):
        for column in names:
            if column not in bars.columns or not bars[column].notna().any():
                raise ValueError(message)
