"""Find stocks whose local daily bars do not reach back as far as they should.

A stock should have bars from its listing day, or from the first day of the local data when it
listed before that. A download that failed part-way can leave a stock with only its later years,
or with nothing; every figure computed over the missing years then silently leaves it out.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

COLUMNS = ["symbol", "name", "expected_start", "first_bar"]
# 上市后头几天停牌、节假日造成的几天差距不算缺口。
TOLERANCE_DAYS = 10


def stocks_missing_history(
    summary: pd.DataFrame,
    master: pd.DataFrame,
    start_date: date,
    end_date: date,
    tolerance_days: int = TOLERANCE_DAYS,
) -> pd.DataFrame:
    """Stocks listed during the range whose bars start late, or that have none (``first_bar`` missing).

    ``summary`` is the repository's per-stock bar summary (indexed by symbol, with ``start``).
    Stocks without a known listing date are left out: there is nothing to compare against.
    """

    if master.empty or not {"symbol", "list_date"} <= set(master.columns):
        return pd.DataFrame(columns=COLUMNS)
    stocks = master.drop_duplicates("symbol").set_index("symbol")
    listed = pd.to_datetime(stocks["list_date"], errors="coerce")
    delisted = pd.to_datetime(stocks.get("delist_date"), errors="coerce") if "delist_date" in stocks else pd.Series(pd.NaT, index=stocks.index)
    first_day, last_day = pd.Timestamp(start_date), pd.Timestamp(end_date)
    in_range = listed.notna() & (listed <= last_day) & (delisted.isna() | (delisted >= first_day))
    expected = listed[in_range].clip(lower=first_day)
    first_bar = pd.to_datetime(summary["start"]).reindex(expected.index) if len(summary) else pd.Series(pd.NaT, index=expected.index)
    missing = first_bar.isna() | (first_bar > expected + pd.Timedelta(days=tolerance_days))
    result = pd.DataFrame({
        "symbol": expected.index[missing],
        "name": stocks["name"].reindex(expected.index)[missing].to_numpy() if "name" in stocks else "",
        "expected_start": expected[missing].to_numpy(),
        "first_bar": first_bar[missing].to_numpy(),
    })
    return result.sort_values("symbol").reset_index(drop=True)
