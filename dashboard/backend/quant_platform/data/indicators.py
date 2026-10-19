"""Daily valuation and turnover indicators, stored next to the bars in ``daily_indicators``.

They come from the data vendor already computed (BaoStock returns them with each daily bar),
so they are kept in a table of their own: the price table stays what was traded, and these
can be backfilled or replaced without touching prices or adjustment factors.

Columns:

- ``pe_ttm``   price / earnings per share, trailing twelve months (negative for a loss)
- ``pb_mrq``   price / book value per share, most recent quarter
- ``ps_ttm``   price / sales per share, trailing twelve months
- ``pcf_ttm``  price / net operating cash flow per share, trailing twelve months
- ``turnover_rate``  shares traded / free-float shares, in percent
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import pandas as pd

from quant_platform.data.normalizers import canonical_symbol

INDICATOR_TABLE = "daily_indicators"
INDICATOR_COLUMNS = ["pe_ttm", "pb_mrq", "ps_ttm", "pcf_ttm", "turnover_rate"]
VALUATION_COLUMNS = ["pe_ttm", "pb_mrq", "ps_ttm", "pcf_ttm"]
INDICATOR_LABELS = {
    "pe_ttm": "市盈率（TTM）",
    "pb_mrq": "市净率（最近一季）",
    "ps_ttm": "市销率（TTM）",
    "pcf_ttm": "市现率（TTM）",
    "turnover_rate": "换手率（%）",
}
# BaoStock ``query_history_k_data_plus`` field -> stored column.
BAOSTOCK_INDICATOR_FIELDS = {
    "peTTM": "pe_ttm",
    "pbMRQ": "pb_mrq",
    "psTTM": "ps_ttm",
    "pcfNcfTTM": "pcf_ttm",
    "turn": "turnover_rate",
}
MISSING_INDICATORS_MESSAGE = "平台还没有估值与换手率数据，管理员更新后就能用。"


def indicator_columns(fields: Iterable[str]) -> list[str]:
    """The indicator columns among the fields a factor or strategy asks for."""

    wanted = set(fields)
    return [column for column in INDICATOR_COLUMNS if column in wanted]


def normalize_baostock_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """BaoStock daily rows -> ``daily_indicators`` rows; empty when the fields were not requested.

    A valuation ratio of exactly zero is how the vendor reports "not available" (no earnings
    figure yet, for example); it is stored as missing rather than as a real ratio.
    """

    present = {field: column for field, column in BAOSTOCK_INDICATOR_FIELDS.items() if field in frame.columns}
    if frame.empty or not present or not {"date", "code"} <= set(frame.columns):
        return pd.DataFrame(columns=["symbol", "trade_date", *INDICATOR_COLUMNS, "source", "ingested_at"])
    result = pd.DataFrame({
        "symbol": frame["code"].astype(str).map(canonical_symbol),
        "trade_date": pd.to_datetime(frame["date"], errors="coerce").dt.normalize(),
    })
    for column in INDICATOR_COLUMNS:
        field = next((name for name, target in present.items() if target == column), None)
        result[column] = pd.to_numeric(frame[field], errors="coerce") if field else float("nan")
    for column in VALUATION_COLUMNS:
        result[column] = result[column].where(result[column] != 0)
    result["source"] = "baostock"
    result["ingested_at"] = datetime.now(UTC)
    result = result.dropna(subset=["symbol", "trade_date"])
    # 五项都没有的行（停牌日、很早的日期）不值得存。
    return result[result[INDICATOR_COLUMNS].notna().any(axis=1)].reset_index(drop=True)


def require_indicator_data(bars: pd.DataFrame, columns: Iterable[str]) -> None:
    """Fail with a message the user can act on when the requested indicators were never downloaded."""

    for column in columns:
        if column not in bars.columns or not bars[column].notna().any():
            raise ValueError(MISSING_INDICATORS_MESSAGE)


def split_daily_indicators(daily: pd.DataFrame, source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separate the indicator columns that travelled with freshly fetched bars.

    Returns the bars without them (what ``daily_bars`` stores) and the ``daily_indicators`` rows.
    """

    present = [column for column in INDICATOR_COLUMNS if column in daily.columns]
    if not present:
        return daily, pd.DataFrame(columns=["symbol", "trade_date", *INDICATOR_COLUMNS, "source", "ingested_at"])
    indicators = daily[["symbol", "trade_date", *present]].copy()
    for column in INDICATOR_COLUMNS:
        if column not in indicators:
            indicators[column] = float("nan")
    indicators["source"] = source
    indicators["ingested_at"] = datetime.now(UTC)
    indicators = indicators[indicators[INDICATOR_COLUMNS].notna().any(axis=1)].reset_index(drop=True)
    return daily.drop(columns=present), indicators
