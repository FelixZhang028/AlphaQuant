"""One stock's quarterly reports, laid out for reading (股票查询 → 财务).

Every report stored for the stock and published by today, newest first: the figures as the
vendor gives them and the ratios derived the same way as in the AI researcher's report. A blank
always comes with the reason, so it never reads as zero. The latest report is set against the
same period a year earlier, because flow figures and the return on equity are cumulative from
the start of the year and only compare like with like.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.ai_research.report import clean, period_name, published_reports

MAX_PERIODS = 48                 # 最多 12 年
# 报告期 -> 最晚公布日期（月, 日）；年报在第二年。
DEADLINES = {3: (4, 30), 6: (8, 31), 9: (10, 31), 12: (4, 30)}
FIGURES = ["revenue", "revenue_yoy", "net_profit", "profit_yoy", "gross_margin", "net_margin", "roe", "debt_ratio",
           "eps_ttm", "current_ratio", "quick_ratio", "total_shares", "float_shares"]
# 和去年同期比：金额看同比增长，比率看差了多少个百分点。
RATIO_CHANGES = ["gross_margin", "net_margin", "roe", "debt_ratio"]
REASONS = {
    "profit_yoy": "数据源没有给净利润同比",
    "gross_margin": "数据源没有给毛利率；银行、证券、保险等金融公司通常没有这一项",
    "net_margin": "数据源没有给净利率",
    "roe": "数据源没有给净资产收益率",
    "debt_ratio": "数据源没有给权益乘数，算不出资产负债率",
}


def _value(x: Any) -> float | None:
    try:
        number = float(x)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _deadline(stat: pd.Timestamp) -> date:
    month, day = DEADLINES[stat.month]
    return date(stat.year + (1 if stat.month == 12 else 0), month, day)


def _row(report: pd.Series, last_year: pd.Series | None) -> dict[str, Any]:
    stat = report["stat_date"]
    revenue, before = _value(report.get("revenue")), _value(last_year.get("revenue")) if last_year is not None else None
    revenue_yoy = revenue / before - 1 if revenue is not None and before is not None and before > 0 else None
    growth = next((v for v in (_value(report.get(k)) for k in ("yoy_parent_net_profit", "yoy_net_profit")) if v is not None), None)
    leverage = _value(report.get("asset_to_equity"))
    row = {
        "period": period_name(stat), "stat_date": stat.date().isoformat(), "pub_date": report["pub_date"].date().isoformat(),
        "revenue": revenue, "revenue_yoy": revenue_yoy, "net_profit": _value(report.get("net_profit")), "profit_yoy": growth,
        "gross_margin": _value(report.get("gross_margin")), "net_margin": _value(report.get("net_margin")),
        "roe": _value(report.get("roe_avg")), "debt_ratio": 1 - 1 / leverage if leverage and leverage > 0 else None,
        "eps_ttm": _value(report.get("eps_ttm")), "current_ratio": _value(report.get("current_ratio")),
        "quick_ratio": _value(report.get("quick_ratio")), "total_shares": _value(report.get("total_shares")),
        "float_shares": _value(report.get("float_shares")),
    }
    missing = {}
    for key in FIGURES:
        if row[key] is not None:
            continue
        if key == "revenue":
            missing[key] = ("数据源没有给这一期的营收：不少公司的一季报、三季报不单独列出主营营收"
                            if stat.month in (3, 9) else "数据源没有给这一期的营收")
        elif key == "revenue_yoy":
            missing[key] = ("这一期没有营收，算不出同比" if revenue is None else
                            "本地没有去年同期的营收，算不出同比" if before is None else "去年同期营收不是正数，不计算同比")
        else:
            missing[key] = REASONS.get(key, "数据源没有给这一项")
    row["missing"] = missing
    return row


def stock_financials(reports: pd.DataFrame, *, today: date) -> dict[str, Any]:
    """``{rows, latest, periods, first_period, last_period, empty_periods, next_report}`` for one stock.

    ``rows`` are newest first. ``latest`` is the newest row with its changes against the same
    period a year earlier (``None`` where that period is not stored)."""

    trade_ts = pd.Timestamp(today)
    stored = reports.copy()
    if not stored.empty:
        stored["stat_date"] = pd.to_datetime(stored["stat_date"])
    # 问过数据源、确认没有财报的报告期（只记了一个空标记）。
    empty = stored[stored["pub_date"].isna()] if not stored.empty else stored
    frame = published_reports(stored, trade_ts) if not stored.empty else stored
    result: dict[str, Any] = {"rows": [], "latest": None, "periods": 0, "first_period": None, "last_period": None,
                              "empty_periods": [], "next_report": None}
    if not frame.empty:
        by_period = {row["stat_date"]: row for _, row in frame.iterrows()}
        shown_periods = sorted(by_period)[-MAX_PERIODS:]
        rows = {stat: _row(by_period[stat], by_period.get(stat - pd.DateOffset(years=1))) for stat in shown_periods}
        newest = max(rows)
        latest, last_year = rows[newest], rows.get(newest - pd.DateOffset(years=1))
        rows = [rows[stat] for stat in sorted(rows, reverse=True)]
        changes = {key: latest[key] - last_year[key] if last_year and latest[key] is not None and last_year[key] is not None else None
                   for key in RATIO_CHANGES}
        result.update(rows=rows, periods=len(rows), first_period=rows[-1]["period"], last_period=latest["period"],
                      latest={**latest, "last_year": last_year["period"] if last_year else None, "changes": changes})
        # 下一份财报：报告期已经结束、还没到最晚公布日期的，告诉读者大概什么时候会有。
        upcoming = newest + pd.offsets.QuarterEnd(1)
        if upcoming.date() < today <= _deadline(upcoming):
            result["next_report"] = {"period": period_name(upcoming), "deadline": _deadline(upcoming).isoformat()}
    if not empty.empty:
        shown = set(result_row["stat_date"] for result_row in result["rows"])
        result["empty_periods"] = [period_name(stat) for stat in sorted(empty["stat_date"].drop_duplicates(), reverse=True)
                                   if stat.date().isoformat() not in shown]
    return clean(result)
