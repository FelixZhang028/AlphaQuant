"""The workspace home page in one request: market overview, the user's stock pool, recent research,
getting-started steps, today's industries, and the data calendar.

Everything is local data or the user's own records. Market figures are for reading the day, not
advice: the page shows index levels, how many stocks rose and fell, and industry averages, never a
list of "top stocks".
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.ai_research import screen
from quant_platform.ai_research.report import period_name
from quant_platform.application.benchmarks import BENCHMARK_NAMES

from ..database import get_conn
from .runtime import market_repository, security_names
from .stock_financials import DEADLINES, _deadline
from .symbols import to_bare, to_canonical

HOME_INDEXES = ("000001.SH", "399001.SZ", "399006.SZ", "000300.SH")
SPARK_DAYS = 60
POOL_ROWS = 100
RECENT_ROWS = 8
INDUSTRY_ROWS = 5
MIN_INDUSTRY_STOCKS = 5


def _num(value: Any, digits: int = 4) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, digits) if pd.notna(number) else None


# --------------------------------------------------------------------------- #
# 市场
# --------------------------------------------------------------------------- #


def indexes(repository: Any) -> list[dict[str, Any]]:
    """The home page's index cards: last close, the day's change and about three months of closes."""

    bars = repository.read_table("benchmark_bars")
    if bars.empty:
        return []
    bars = bars[bars["symbol"].isin(HOME_INDEXES)].copy()
    bars["trade_date"] = pd.to_datetime(bars["trade_date"])
    cards = []
    for symbol in HOME_INDEXES:
        rows = bars[bars["symbol"] == symbol].sort_values("trade_date").drop_duplicates("trade_date", keep="last")
        closes = pd.to_numeric(rows["raw_close"], errors="coerce").dropna()
        if closes.empty:
            continue
        last = rows.loc[closes.index[-1]]
        previous = _num(last.get("pre_close")) or (float(closes.iloc[-2]) if len(closes) > 1 else None)
        change = float(closes.iloc[-1]) / previous - 1 if previous else None
        cards.append({"symbol": symbol, "name": BENCHMARK_NAMES.get(symbol, symbol), "date": last["trade_date"].date().isoformat(),
                      "close": _num(closes.iloc[-1], 2), "change": _num(change),
                      "series": [_num(value, 2) for value in closes.iloc[-SPARK_DAYS:]]})
    return cards


def breadth(table: pd.DataFrame, day: pd.Timestamp) -> dict[str, Any]:
    """How many stocks rose, fell or stayed flat on the day, limit moves, and total turnover."""

    trading = table[~table["is_suspended"]]
    change = pd.to_numeric(trading["ret_1d"], errors="coerce")
    return {"day": day.date().isoformat(), "total": int(len(trading)),
            "up": int((change > 0).sum()), "down": int((change < 0).sum()), "flat": int((change == 0).sum()),
            "limit_up": int(trading["at_up_limit"].sum()), "limit_down": int(trading["at_down_limit"].sum()),
            "amount": _num(pd.to_numeric(trading["amount_today"], errors="coerce").sum(), 0),
            "suspended": int(table["is_suspended"].sum())}


def industries(table: pd.DataFrame, day: pd.Timestamp) -> dict[str, Any]:
    """Average change of the day per industry (CSRC), the five highest and the five lowest; ST stocks left out."""

    rows = table[~table["is_suspended"] & ~table["is_st"] & table["industry"].astype(bool)]
    grouped = rows.assign(change=pd.to_numeric(rows["ret_1d"], errors="coerce")).dropna(subset=["change"]).groupby("industry")["change"]
    stats = pd.DataFrame({"change": grouped.mean(), "count": grouped.size(), "up": grouped.apply(lambda c: int((c > 0).sum()))})
    stats = stats[stats["count"] >= MIN_INDUSTRY_STOCKS].sort_values("change", ascending=False)
    pack = lambda frame: [{"name": name, "change": _num(row["change"]), "count": int(row["count"]), "up": int(row["up"])}  # noqa: E731
                          for name, row in frame.iterrows()]
    return {"day": day.date().isoformat(), "count": int(len(stats)),
            "up": pack(stats.head(INDUSTRY_ROWS)), "down": pack(stats.tail(INDUSTRY_ROWS).iloc[::-1])}


def pool(table: pd.DataFrame, symbols: list[str], names: dict[str, str]) -> list[dict[str, Any]]:
    """The user's stock pool with the latest close, the day's change and 20 trading days' change."""

    rows = []
    for code in symbols[:POOL_ROWS]:
        symbol = to_canonical(code)
        if symbol in table.index:
            row = table.loc[symbol]
            rows.append({"symbol": to_bare(symbol), "name": str(row["name"]), "close": _num(row["close"], 2),
                         "change": _num(row["ret_1d"]), "ret_20d": _num(row["ret_20d"]), "suspended": bool(row["is_suspended"]),
                         "st": bool(row["is_st"]), "industry": str(row["industry"] or "")})
        else:
            rows.append({"symbol": to_bare(symbol), "name": names.get(symbol, to_bare(symbol)), "close": None, "change": None,
                         "ret_20d": None, "suspended": False, "st": False, "industry": "", "missing": True})
    return rows


# --------------------------------------------------------------------------- #
# 用户自己的研究
# --------------------------------------------------------------------------- #


def research(user_id: int) -> dict[str, Any]:
    """Recent backtests, analyses, Q&A and strategies (newest first), counts, and the getting-started steps."""

    with get_conn() as conn:
        backtests = conn.execute("SELECT id, strategy, from_date, to_date, status, result, created_at FROM backtests "
                                 "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, RECENT_ROWS)).fetchall()
        briefs = conn.execute("SELECT id, symbol, name, trade_date, created_at FROM stock_briefs WHERE user_id = ? "
                              "ORDER BY created_at DESC LIMIT ?", (user_id, RECENT_ROWS)).fetchall()
        chats = conn.execute("SELECT id, title, updated_at FROM ai_chats WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
                             (user_id, RECENT_ROWS)).fetchall()
        packages = conn.execute("SELECT package_id, name, created_at FROM strategy_packages WHERE user_id = ? "
                                "ORDER BY created_at DESC LIMIT ?", (user_id, RECENT_ROWS)).fetchall()
        count = lambda sql: int(conn.execute(sql, (user_id,)).fetchone()[0] or 0)  # noqa: E731
        counts = {"strategies": count("SELECT COUNT(*) FROM strategy_packages WHERE user_id = ?"),
                  "backtests": count("SELECT COUNT(*) FROM backtests WHERE user_id = ? AND status = '完成'"),
                  "briefs": count("SELECT COUNT(*) FROM stock_briefs WHERE user_id = ?"),
                  "chats": count("SELECT COUNT(*) FROM ai_chats WHERE user_id = ?")}
        pool_saved = conn.execute("SELECT symbols FROM universe WHERE user_id = ?", (user_id,)).fetchone()
    items = []
    for row in backtests:
        result = json.loads(row["result"]) if row["result"] else {}
        done = row["status"] == "完成"
        detail = (f"总收益 {float(result['total_return']):+.2f}% · 最大回撤 {float(result['max_drawdown']):.2f}%"
                  if done and result.get("total_return") is not None and result.get("max_drawdown") is not None else str(row["status"]))
        items.append({"kind": "backtest", "label": "回测", "title": f"{row['strategy']}（{row['from_date']} ~ {row['to_date']}）",
                      "detail": detail, "at": row["created_at"], "view": "backtest-review", "context": {"run": row["id"]},
                      "value": _num(result.get("total_return"), 2) if done else None})
    for row in briefs:
        items.append({"kind": "brief", "label": "AI 研究员", "title": f"{row['name']}（{to_bare(row['symbol'])}）",
                      "detail": f"数据截至 {row['trade_date']}", "at": row["created_at"], "view": "agent-lab", "context": {"brief": row["id"]}})
    for row in chats:
        items.append({"kind": "chat", "label": "AI 问答", "title": row["title"], "detail": "", "at": row["updated_at"],
                      "view": "", "context": {"chat": row["id"]}})
    for row in packages:
        items.append({"kind": "strategy", "label": "策略", "title": row["name"], "detail": "保存的规则策略", "at": row["created_at"],
                      "view": "backtest-review", "context": {"strategy": f"package:{row['package_id']}"}})
    items.sort(key=lambda item: str(item["at"]), reverse=True)
    pool_set = bool(pool_saved and json.loads(pool_saved["symbols"] or "[]"))
    steps = [
        {"key": "pool", "label": "设置自己的股票池", "done": pool_set, "view": "universe"},
        {"key": "strategy", "label": "保存一个规则策略", "done": counts["strategies"] > 0, "view": "strategy-hub"},
        {"key": "backtest", "label": "跑完第一次回测", "done": counts["backtests"] > 0, "view": "backtest-review"},
        {"key": "brief", "label": "用 AI 研究员分析一只股票", "done": counts["briefs"] > 0, "view": "agent-lab"},
    ]
    return {"recent": items[:RECENT_ROWS], "counts": counts, "steps": steps}


# --------------------------------------------------------------------------- #
# 数据日历
# --------------------------------------------------------------------------- #


def report_seasons(repository: Any, listed: int, today: date) -> list[dict[str, Any]]:
    """The reporting periods being published now (the quarter has ended, the deadline has not passed),
    each with how many stocks have published it. In April the annual report and the first quarter
    overlap; outside the reporting windows the list is empty."""

    latest_end = (pd.Timestamp(today).to_period("Q").start_time - pd.Timedelta(days=1)).normalize()
    ends = [latest_end - pd.offsets.QuarterEnd(n) for n in range(4)]
    active = [end for end in ends if end.month in DEADLINES and end.date() < today <= _deadline(end)]
    if not active:
        return []
    reports = repository.get_fundamentals()
    seasons = []
    for end in sorted(active, key=lambda end: (_deadline(end), end)):   # 截止日相同时，早的报告期在前
        published = 0
        if not reports.empty:
            stat, pub = pd.to_datetime(reports["stat_date"]), pd.to_datetime(reports["pub_date"])
            published = int(reports.loc[(stat == end) & pub.notna() & (pub <= pd.Timestamp(today)), "symbol"].nunique())
        deadline = _deadline(end)
        seasons.append({"period": period_name(end), "deadline": deadline.isoformat(), "published": published,
                        "listed": listed, "days_left": (deadline - today).days})
    return seasons


def build(user: dict[str, Any], universe: list[str], today: date) -> dict[str, Any]:
    repository = market_repository()
    names = security_names()
    out: dict[str, Any] = {"indexes": indexes(repository), **research(user["id"])}
    try:
        day, table = screen.snapshot(repository, names)
    except ValueError:
        day, table = None, None
    if table is not None:
        out.update(breadth=breadth(table, day), industries=industries(table, day), pool=pool(table, universe, names))
    else:
        out.update(breadth=None, industries=None, pool=pool(pd.DataFrame(columns=["name"]), universe, names))
    out["report_seasons"] = report_seasons(repository, out["breadth"]["total"] if out.get("breadth") else 0, today)
    return out
