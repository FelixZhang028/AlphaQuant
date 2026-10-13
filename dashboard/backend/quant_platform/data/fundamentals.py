"""Quarterly financial reports, stored in ``quarterly_fundamentals`` and used point in time.

One row per stock and reporting period (``stat_date``, the quarter end) with the day the report
was published (``pub_date``). A value may only be used from its publication day on: joining to
daily bars always goes through :func:`point_in_time`, never through ``stat_date``.

Flow figures are cumulative within the fiscal year, as reported (the half-year report covers
six months). Ratios and year-on-year changes are comparable across periods; levels are not.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime

import pandas as pd

from quant_platform.data.normalizers import canonical_symbol

FUNDAMENTALS_TABLE = "quarterly_fundamentals"
# BaoStock endpoint -> {vendor field: stored column}.
BAOSTOCK_FUNDAMENTAL_FIELDS: dict[str, dict[str, str]] = {
    "profit": {
        "roeAvg": "roe_avg",                 # 净资产收益率（平均），年初至报告期
        "npMargin": "net_margin",            # 销售净利率
        "gpMargin": "gross_margin",          # 销售毛利率（银行等没有）
        "netProfit": "net_profit",           # 净利润（元），年初至报告期
        "epsTTM": "eps_ttm",                 # 每股收益（TTM）
        "MBRevenue": "revenue",              # 主营营业收入（元），部分公司只在半年报和年报披露
        "totalShare": "total_shares",        # 总股本（股）
        "liqaShare": "float_shares",         # 流通股本（股）
    },
    "growth": {
        "YOYEquity": "yoy_equity",           # 净资产同比增长
        "YOYAsset": "yoy_asset",             # 总资产同比增长
        "YOYNI": "yoy_net_profit",           # 净利润同比增长
        "YOYEPSBasic": "yoy_eps",            # 基本每股收益同比增长
        "YOYPNI": "yoy_parent_net_profit",   # 归属母公司股东净利润同比增长
    },
    "balance": {
        "currentRatio": "current_ratio",     # 流动比率
        "quickRatio": "quick_ratio",         # 速动比率
        "assetToEquity": "asset_to_equity",  # 权益乘数（总资产 / 净资产）
    },
}
FUNDAMENTAL_COLUMNS = [column for fields in BAOSTOCK_FUNDAMENTAL_FIELDS.values() for column in fields.values()]
FUNDAMENTAL_LABELS = {
    "roe_avg": "净资产收益率", "net_margin": "销售净利率", "gross_margin": "销售毛利率", "net_profit": "净利润",
    "eps_ttm": "每股收益（TTM）", "revenue": "主营营业收入", "total_shares": "总股本", "float_shares": "流通股本",
    "yoy_equity": "净资产同比增长", "yoy_asset": "总资产同比增长", "yoy_net_profit": "净利润同比增长",
    "yoy_eps": "每股收益同比增长", "yoy_parent_net_profit": "归母净利润同比增长",
    "current_ratio": "流动比率", "quick_ratio": "速动比率", "asset_to_equity": "权益乘数",
}
STORED_COLUMNS = ["symbol", "stat_date", "pub_date", *FUNDAMENTAL_COLUMNS, "source", "ingested_at"]
# 厂商偶尔把一份报告的这些比率按百分数给出（见 normalize_baostock_quarter）。
PERCENT_SCALE_SUSPECTS = ["roe_avg", "gross_margin", "yoy_equity", "yoy_asset", "yoy_net_profit", "yoy_eps", "yoy_parent_net_profit"]
# 一份财报最多用这么多天：公司不再披露（长期停牌、退市）时，不拿一年多以前的数字当现在的。
MAX_REPORT_AGE_DAYS = 370
MISSING_FUNDAMENTALS_MESSAGE = "本地还没有财务数据，请先在「数据更新」里下载后再使用。"


def quarter_end(year: int, quarter: int) -> date:
    return date(year, quarter * 3, 31 if quarter in (1, 4) else 30)


def quarters_between(first: date, last: date) -> list[tuple[int, int]]:
    """Every (year, quarter) whose quarter end falls in ``[first, last]``."""

    result = []
    for year in range(first.year, last.year + 1):
        for quarter in (1, 2, 3, 4):
            if first <= quarter_end(year, quarter) <= last:
                result.append((year, quarter))
    return result


def fundamental_columns(fields: Iterable[str]) -> list[str]:
    """The quarterly-report columns among the fields a factor or strategy asks for."""

    wanted = set(fields)
    return [column for column in FUNDAMENTAL_COLUMNS if column in wanted]


def normalize_baostock_quarter(symbol: str, year: int, quarter: int, responses: dict[str, pd.DataFrame]) -> dict | None:
    """One stored row from the endpoint responses for one stock and quarter; ``None`` if none answered.

    The publication day is the latest one any endpoint reports, so nothing is used before
    every part of the row was public.
    """

    row: dict = {column: float("nan") for column in FUNDAMENTAL_COLUMNS}
    published: list[pd.Timestamp] = []
    for endpoint, fields in BAOSTOCK_FUNDAMENTAL_FIELDS.items():
        frame = responses.get(endpoint)
        if frame is None or frame.empty:
            continue
        record = frame.iloc[0]
        day = pd.to_datetime(record.get("pubDate"), errors="coerce")
        if pd.notna(day):
            published.append(day)
        for vendor, column in fields.items():
            if vendor in frame.columns:
                row[column] = pd.to_numeric(pd.Series([record[vendor]]), errors="coerce").iloc[0]
    if not published:
        return None
    if row["gross_margin"] > 1:
        # 毛利率不可能超过 100%：这份报告的比率是按百分数给的（个别上市前的报告如此），
        # 而且同一份里各项的口径并不一致，所以不去猜怎么换算，受影响的几项都按缺失处理。
        for column in PERCENT_SCALE_SUSPECTS:
            row[column] = float("nan")
    return {"symbol": canonical_symbol(symbol), "stat_date": pd.Timestamp(quarter_end(year, quarter)),
            "pub_date": max(published).normalize(), **row, "source": "baostock", "ingested_at": datetime.now(UTC)}


def checked_empty_row(symbol: str, year: int, quarter: int) -> dict:
    """A marker for "asked, the vendor has no report for this period": keeps old gaps from being asked again."""

    return {"symbol": canonical_symbol(symbol), "stat_date": pd.Timestamp(quarter_end(year, quarter)), "pub_date": pd.NaT,
            **{column: float("nan") for column in FUNDAMENTAL_COLUMNS}, "source": "baostock", "ingested_at": datetime.now(UTC)}


def point_in_time(days: pd.DataFrame, reports: pd.DataFrame, columns: list[str],
                  max_age_days: int = MAX_REPORT_AGE_DAYS) -> pd.DataFrame:
    """For each (symbol, trade_date) the values of the newest report already published that day.

    ``days`` has ``symbol`` and ``trade_date``; the result has the same rows, in the same order,
    with ``columns`` added. A report counts from its publication day. When an older period is
    published after a newer one (a late correction), the newer period stays in force. A report
    older than ``max_age_days`` gives missing values.
    """

    result = days[["symbol", "trade_date"]].copy()
    result["trade_date"] = pd.to_datetime(result["trade_date"]).astype("datetime64[ns]")
    if reports.empty:
        return result.assign(**{column: float("nan") for column in columns})
    published = reports.dropna(subset=["pub_date"]).copy()
    published["pub_date"] = pd.to_datetime(published["pub_date"]).astype("datetime64[ns]")
    published["stat_date"] = pd.to_datetime(published["stat_date"]).astype("datetime64[ns]")
    published = published.sort_values(["symbol", "pub_date", "stat_date"])
    newest = published.groupby("symbol")["stat_date"].cummax()
    published = published[published["stat_date"] >= newest].sort_values(["pub_date", "stat_date"])
    order = result.assign(_row=range(len(result))).sort_values("trade_date")
    joined = pd.merge_asof(
        order, published[["symbol", "pub_date", *columns]], left_on="trade_date", right_on="pub_date",
        by="symbol", direction="backward",
    )
    stale = (joined["trade_date"] - joined["pub_date"]).dt.days > max_age_days
    joined.loc[stale, columns] = float("nan")
    joined = joined.sort_values("_row")
    for column in columns:
        result[column] = joined[column].to_numpy()
    return result
