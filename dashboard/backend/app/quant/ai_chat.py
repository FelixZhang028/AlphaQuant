"""Run the AI Q&A's lookups on local data: each one becomes a data block the answer rests on.

A block is ``{kind, title, as_of, columns, rows, notes, symbols}`` (all text, ready to show and to
send to the model) or ``{kind, title, error}`` when the lookup could not be answered. Everything
is read-only and local; a user only ever sees their own backtests.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date
from typing import Any

import pandas as pd

from quant_platform.ai_research import screen
from quant_platform.ai_research.decisions import backtest_facts
from quant_platform.ai_research.facts import stock_facts

from ..database import get_conn
from .benchmark_view import benchmark_comparison
from .run_evidence import run_directory, with_run_evidence
from .runtime import build_data_center_service, build_factor_registry, market_repository, security_names
from .stock_financials import stock_financials
from .symbols import to_bare, to_canonical

FINANCIAL_ROWS = 8
FACTOR_ROWS = 8
BACKTEST_ROWS = 10
DATA_STATUS_SECONDS = 600
_STATUS_CACHE: dict[str, Any] = {}
_STATUS_LOCK = threading.Lock()


class NotAnswerable(ValueError):
    """A lookup the user's question pointed at but local data cannot answer; the message is shown."""


# --------------------------------------------------------------------------- #
# 股票代码和名称
# --------------------------------------------------------------------------- #


def resolve_symbol(text: str, names: dict[str, str]) -> tuple[str, str]:
    """``(canonical symbol, name)`` for a code or a (part of a) stock name."""

    text = str(text).strip()
    if re.fullmatch(r"\d{6}(\.[A-Za-z]{2})?", text):
        symbol = to_canonical(text)
        return symbol, names.get(symbol) or symbol
    exact = [symbol for symbol, name in names.items() if name == text]
    if exact:
        return exact[0], text
    partial = [(symbol, name) for symbol, name in names.items() if text and text in name]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise NotAnswerable(f"没有找到名称里有“{text}”的股票，可以换成 6 位代码再问。")
    shown = "、".join(f"{name}（{to_bare(symbol)}）" for symbol, name in partial[:6])
    raise NotAnswerable(f"名称里有“{text}”的股票有好几只：{shown}{'等' if len(partial) > 6 else ''}，请说得具体一点。")


def _yi(x: Any) -> str:
    return f"{float(x) / 1e8:,.1f} 亿" if x is not None else "—"


def _pct(x: Any, signed: bool = False) -> str:
    if x is None:
        return "—"
    return f"{float(x) * 100:+.1f}%" if signed else f"{float(x) * 100:.1f}%"


# --------------------------------------------------------------------------- #
# 各种查询
# --------------------------------------------------------------------------- #


def stock_block(symbol_text: str, names: dict[str, str]) -> dict[str, Any]:
    symbol, name = resolve_symbol(symbol_text, names)
    try:
        facts = stock_facts(market_repository(), symbol, name=name, with_report=False)
    except ValueError as exc:
        raise NotAnswerable(str(exc)) from exc
    notes = [f"本地缺少：{item['group']}（{item['reason']}）" for item in facts.missing] + list(facts.notes)
    return {"kind": "stock", "title": f"{name}（{to_bare(symbol)}）的数据", "as_of": facts.trade_date.isoformat(),
            "columns": ["项目", "数值", "日期"], "rows": [[f.label, f.text, f.as_of or "—"] for f in facts.facts],
            "notes": notes, "symbols": [to_bare(symbol)]}


def financials_block(symbol_text: str, names: dict[str, str], today: date) -> dict[str, Any]:
    symbol, name = resolve_symbol(symbol_text, names)
    data = stock_financials(market_repository().get_fundamentals([symbol]), today=today)
    title = f"{name}（{to_bare(symbol)}）的历期财报"
    if not data["periods"]:
        raise NotAnswerable(f"本地还没有{name}的财报。")
    columns = ["报告期", "公布日期", "营收", "营收同比", "净利润", "净利润同比", "毛利率", "净利率", "净资产收益率", "资产负债率"]
    rows = [[row["period"], row["pub_date"], _yi(row["revenue"]), _pct(row["revenue_yoy"], True), _yi(row["net_profit"]),
             _pct(row["profit_yoy"], True), _pct(row["gross_margin"]), _pct(row["net_margin"]), _pct(row["roe"]), _pct(row["debt_ratio"])]
            for row in data["rows"][:FINANCIAL_ROWS]]
    notes = ["营收、净利润、净资产收益率都是年初至报告期累计的（半年报是前 6 个月的合计），不同季度之间不能直接比较。",
             f"本地一共有 {data['periods']} 期财报（{data['first_period']} ～ {data['last_period']}）。"]
    if data.get("next_report"):
        notes.append(f"下一份 {data['next_report']['period']} 最晚 {data['next_report']['deadline']} 公布。")
    return {"kind": "financials", "title": title, "as_of": data["rows"][0]["pub_date"], "columns": columns, "rows": rows,
            "notes": notes, "symbols": [to_bare(symbol)]}


def _snapshot(names: dict[str, str]):
    try:
        return screen.snapshot(market_repository(), names)
    except ValueError as exc:
        raise NotAnswerable(str(exc)) from exc


def rank_block(lookup: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    day, table = _snapshot(names)
    industry_of = resolve_symbol(lookup["industry_of"], names)[0] if lookup.get("industry_of") else None
    try:
        return screen.rank(table, day, lookup["metric"], order=lookup["order"], scope=lookup["scope"],
                           industry=lookup.get("industry", ""), industry_of=industry_of, limit=lookup["limit"])
    except ValueError as exc:
        raise NotAnswerable(str(exc)) from exc


def compare_block(lookup: dict[str, Any], names: dict[str, str]) -> dict[str, Any]:
    day, table = _snapshot(names)
    symbols, notes = [], []
    for text in lookup["symbols"]:
        try:
            symbols.append(resolve_symbol(text, names)[0])
        except NotAnswerable as exc:
            notes.append(str(exc))
    block = screen.compare(table, day, symbols, lookup.get("metrics"))
    block["notes"] = notes + block["notes"]
    return block


def _backtest_rows(user: dict, limit: int) -> list[Any]:
    with get_conn() as conn:
        return conn.execute("SELECT id, strategy, from_date, to_date, status, result, created_at FROM backtests "
                            "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user["id"], limit)).fetchall()


def backtests_block(user: dict) -> dict[str, Any]:
    rows = _backtest_rows(user, BACKTEST_ROWS)
    if not rows:
        raise NotAnswerable("你还没有回测记录。")
    out = []
    for row in rows:
        result = json.loads(row["result"]) if row["result"] else {}
        metric = lambda key: f"{float(result[key]):.2f}%" if result.get(key) is not None else "—"  # noqa: E731
        out.append([str(row["id"]), str(row["strategy"]), f"{row['from_date']} ~ {row['to_date']}", str(row["status"]),
                    metric("total_return"), metric("annual_return"), metric("max_drawdown"),
                    f"{float(result['sharpe']):.2f}" if result.get("sharpe") is not None else "—", str(row["created_at"])[:10]])
    return {"kind": "backtests", "title": f"你最近的 {len(out)} 次回测", "as_of": str(rows[0]["created_at"])[:10],
            "columns": ["编号", "策略", "回测区间", "状态", "总收益", "年化收益", "最大回撤", "夏普比率", "运行日期"],
            "rows": out, "notes": ["收益、回撤都是这次回测里的结果，不代表以后。"]}


def drawdown_window(dates: list[str], equity: list[float]) -> dict[str, Any] | None:
    """The deepest fall of the equity curve: from which peak, to which low, and when it was made up."""

    curve = pd.Series([float(v) for v in equity], index=pd.to_datetime(dates)) if dates and len(dates) == len(equity) else None
    if curve is None or len(curve) < 2:
        return None
    peaks = curve.cummax()
    falls = curve / peaks - 1
    low = falls.idxmin()
    if falls[low] >= 0:
        return None
    peak = curve[:low].idxmax()
    after = curve[low:]
    recovered = after[after >= curve[peak]]
    return {"peak": peak.date().isoformat(), "low": low.date().isoformat(), "depth": float(falls[low]),
            "recovered": recovered.index[0].date().isoformat() if not recovered.empty else None,
            "days": int(((curve.index > peak) & (curve.index <= low)).sum())}


def monthly_returns(dates: list[str], equity: list[float]) -> pd.Series:
    if not dates or len(dates) != len(equity):
        return pd.Series(dtype=float)
    curve = pd.Series([float(v) for v in equity], index=pd.to_datetime(dates))
    ends = curve.groupby(curve.index.to_period("M")).last()
    starts = ends.shift(1)
    starts.iloc[0] = curve.iloc[0]
    return ends / starts - 1


def backtest_block(user: dict, ref: str) -> dict[str, Any]:
    if str(ref).lower() in ("", "latest", "最近", "最近一次"):
        rows = _backtest_rows(user, 1)
        if not rows:
            raise NotAnswerable("你还没有回测记录。")
        bid = int(rows[0]["id"])
    else:
        digits = re.sub(r"\D", "", str(ref))
        if not digits:
            raise NotAnswerable("回测编号无效。")
        bid = int(digits)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM backtests WHERE id = ? AND user_id = ?", (bid, user["id"])).fetchone()
    if row is None:
        raise NotAnswerable(f"没有找到你的第 {bid} 号回测。")
    result = with_run_evidence(json.loads(row["result"]) if row["result"] else {})
    if not result.get("equity"):
        raise NotAnswerable(f"第 {bid} 号回测没有完成（状态：{row['status']}），没有结果可以看。")
    try:
        benchmark = benchmark_comparison(run_directory(result))
    except Exception:  # noqa: BLE001 - 没有基准时照样给出回测自己的数字
        benchmark = None
    facts = backtest_facts({"from_date": row["from_date"], "to_date": row["to_date"]}, result, benchmark)
    rows = [[f"{fact.group} · {fact.label}", fact.text] for fact in facts]
    dates, equity = result.get("nav_dates") or [], result.get("equity") or []
    window = drawdown_window(dates, equity)
    if window:
        end = f"，{window['recovered']} 回到之前的高点" if window["recovered"] else "，到回测结束还没有回到之前的高点"
        rows.append(["收益与风险 · 最大回撤发生在", f"{window['peak']} 的高点到 {window['low']} 的低点（{window['days']} 个交易日，"
                     f"{window['depth'] * 100:.2f}%）{end}"])
    months = monthly_returns(dates, equity).dropna()
    if len(months) >= 3:
        best, worst = months.nlargest(3), months.nsmallest(3)
        rows.append(["收益与风险 · 收益最好的月份", "、".join(f"{p}（{v * 100:+.1f}%）" for p, v in best.items())])
        rows.append(["收益与风险 · 收益最差的月份", "、".join(f"{p}（{v * 100:+.1f}%）" for p, v in worst.items())])
    return {"kind": "backtest", "title": f"第 {bid} 号回测：{row['strategy']}", "as_of": str(row["created_at"])[:10],
            "columns": ["项目", "数值"], "rows": rows, "notes": ["这些是这次回测里的结果，不代表以后。"], "backtest": bid}


def factors_block(user: dict, keyword: str) -> dict[str, Any]:
    word = keyword.strip().lower()
    found = [f for f in build_factor_registry(user).list()
             if word in " ".join([f.name, f.display_name or "", f.category, f.description or ""]).lower()]
    if not found:
        raise NotAnswerable(f"因子库里没有和“{keyword}”有关的因子。")
    rows = [[f.display_name or f.name, f.name, f.category, "越大越好" if f.direction == 1 else "越小越好" if f.direction == -1 else "—",
             (f.description or "")[:80], (f.formula or "")[:80]] for f in found[:FACTOR_ROWS]]
    notes = [f"一共找到 {len(found)} 个，这里列出前 {len(rows)} 个。"] if len(found) > len(rows) else []
    return {"kind": "factors", "title": f"因子库里和“{keyword}”有关的因子", "as_of": "",
            "columns": ["因子", "代号", "类别", "方向", "说明", "计算方法"], "rows": rows, "notes": notes}


def data_status_block(user: dict) -> dict[str, Any]:
    with _STATUS_LOCK:
        cached = _STATUS_CACHE.get("status")
        if cached and time.monotonic() - cached[0] < DATA_STATUS_SECONDS:
            status = cached[1]
        else:
            status = None
    if status is None:
        status = build_data_center_service(user).closed_loop_status()
        with _STATUS_LOCK:
            _STATUS_CACHE["status"] = (time.monotonic(), status)
    rows = [["日线行情", f"{status.get('bars_symbols', 0)} 只股票", f"{status.get('bars_min') or '—'} 至 {status.get('bars_max') or '—'}"]]
    indicators = status.get("indicators") or {}
    if indicators:
        rows.append(["估值与换手率", f"{indicators.get('symbols', 0)} 只股票（{indicators.get('missing_symbols', 0)} 只没有）",
                     f"{indicators.get('start_date') or '—'} 至 {indicators.get('end_date') or '—'}"])
    fundamentals = status.get("fundamentals") or {}
    if fundamentals:
        rows.append(["财务数据", f"{fundamentals.get('symbols', 0)} 只股票，{fundamentals.get('reports', 0)} 份财报",
                     f"最新报告期 {fundamentals.get('latest_stat_date') or '—'}，最新公布 {fundamentals.get('latest_pub_date') or '—'}"])
    industry = status.get("industry") or {}
    if industry:
        rows.append(["行业分类", f"{industry.get('symbols', 0)} 只股票，{industry.get('snapshots', 0)} 个时点",
                     f"{industry.get('start_date') or '—'} 至 {industry.get('end_date') or '—'}"])
    for item in status.get("index_constituents") or []:
        rows.append([f"{item.get('name')}成分股", f"现在 {item.get('members', 0)} 只", f"{item.get('start_date') or '—'} 至 {item.get('end_date') or '—'}"])
    rows.append(["分红送转", f"{status.get('corporate_action_rows', 0)} 条记录", "—"])
    rows.append(["历史股票池", f"{status.get('membership_symbols', 0)} 只股票（已退市 {status.get('master_delisted', 0)} 只）", "—"])
    return {"kind": "data_status", "title": "平台现在有哪些数据", "as_of": status.get("bars_max") or "",
            "columns": ["数据", "覆盖", "时间范围"], "rows": rows,
            "notes": ["“时间范围”是所有股票里最早到最晚的日期，不代表每只股票都有这么长的历史。",
                      "估值与换手率、财务数据的历史长短，会影响相关因子能研究多长时间。"]}


TITLES = {"stock": "股票数据", "financials": "历期财报", "rank": "排序", "compare": "比较", "backtests": "回测记录",
          "backtest": "回测结果", "factors": "因子说明", "data_status": "平台数据"}


def run_lookups(lookups: list[dict[str, Any]], user: dict, today: date) -> list[dict[str, Any]]:
    """Each lookup's block, in order; a lookup that fails gives a block that says why."""

    names = security_names()
    blocks = []
    for lookup in lookups:
        kind = lookup["type"]
        try:
            if kind == "stock":
                block = stock_block(lookup["symbol"], names)
            elif kind == "financials":
                block = financials_block(lookup["symbol"], names, today)
            elif kind == "rank":
                block = rank_block(lookup, names)
            elif kind == "compare":
                block = compare_block(lookup, names)
            elif kind == "backtests":
                block = backtests_block(user)
            elif kind == "backtest":
                block = backtest_block(user, lookup.get("id", "latest"))
            elif kind == "factors":
                block = factors_block(user, lookup["keyword"])
            else:
                block = data_status_block(user)
        except NotAnswerable as exc:
            block = {"kind": kind, "title": TITLES.get(kind, kind), "error": str(exc), "as_of": ""}
        blocks.append(block)
    return blocks


def describe_context(context: dict[str, Any] | None, user: dict) -> dict[str, Any]:
    """The page context the browser sent, checked: a known stock name, and only the user's own backtest."""

    context = context or {}
    out: dict[str, Any] = {}
    page = str(context.get("page") or "").strip()[:20]
    if page:
        out["page"] = page
    symbol = str(context.get("symbol") or "").strip()
    if re.fullmatch(r"\d{6}(\.[A-Za-z]{2})?", symbol):
        canonical = to_canonical(symbol)
        name = security_names().get(canonical)
        if name:
            out["stock"] = f"{name}（{to_bare(canonical)}）"
    backtest = re.sub(r"\D", "", str(context.get("backtest") or ""))
    if backtest:
        with get_conn() as conn:
            found = conn.execute("SELECT 1 FROM backtests WHERE id = ? AND user_id = ?", (int(backtest), user["id"])).fetchone()
        if found:
            out["backtest"] = int(backtest)
    return out
