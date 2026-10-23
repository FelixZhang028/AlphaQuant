"""The AI reading of a whole screen result: what kind of stocks the user's own conditions picked out.

The model gets a facts table of the top stocks and a few group statistics, all from local data, and
writes a short summary and four lists of points: what the stocks have in common, which ones stand
out, risk clues, and what to check next. Each point cites the facts it rests on. A point is dropped
when it cites nothing known, when one of its numbers is not in the facts it cites, or when it gives
trading instructions or talks about where prices are heading -- the same checks as the reading of
one stock (``brief.py``). It never ranks the stocks or says which ones to look at first.
"""

from __future__ import annotations

from datetime import date
from math import isfinite, sqrt
from statistics import median
from typing import Any

import pandas as pd

from quant_platform.ai_research.brief import RULES, BriefFormatError, _gives_orders, _numbers_supported
from quant_platform.ai_research.facts import Fact, StockFacts

MAX_STOCKS = 30
HISTORY_DAYS = 400               # 自然日：够算近一年最高价和 60 日波动率
SECTIONS = {"common_points": 5, "outlier_points": 4, "risk_points": 5, "check_points": 3}
MAX_EVIDENCE = 6
MAX_POINT_CHARS = 120
MAX_SUMMARY_CHARS = 200

SCREEN_SYSTEM = f"""你是 A 股研究助手。用户用自己设的条件筛出了一组股票，请帮他读懂“这组条件筛出了一批什么样的股票”。
{RULES}
6. 不要给股票排名，也不要说哪只更值得关注、更好或更差；只描述数据里的共同点、差别和需要核查的地方。
7. 说“有几只”时可以写只数；其他数字照抄数据表，不要自己设门槛（例如不要写“超过 30%”，直接写数据表里的数值）。
8. 每条要点在 evidence 里写出它依据的数据编号（1～6 个，只能用数据表第一列里的编号），每条不超过 60 个字。

只输出一个 JSON 对象，不要输出别的文字：
{{"summary": "一到两句话概括这组股票，不超过 100 字",
"common_points": [{{"text": "这组股票的一个共同特征", "evidence": ["数据编号"]}}],
"outlier_points": [{{"text": "和其他股票明显不同的一只或几只", "evidence": ["数据编号"]}}],
"risk_points": [{{"text": "数据里的一条风险线索", "evidence": ["数据编号"]}}],
"check_points": [{{"text": "接下来值得核查的一件事", "evidence": ["数据编号"]}}]}}
common_points 2～5 条，outlier_points 0～4 条，risk_points 1～5 条，check_points 0～3 条。"""


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:+.2f}%"


def _amount(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value / 1e8:.2f} 亿元" if value >= 1e8 else f"{value / 1e4:.0f} 万元"


def _industry_name(value: Any) -> str:
    """“J66货币金融服务” -> “货币金融服务”：证监会分类前面的代码对读的人没有用。"""

    import re

    if value is None or (isinstance(value, float) and not isfinite(value)) or not str(value).strip():
        return ""
    return re.sub(r"^[A-Z]\d{2}\s*", "", str(value).strip())


def _metrics(group: pd.DataFrame) -> dict[str, float | None]:
    """One stock's numbers on its last day, from its history (oldest first)."""

    close = pd.to_numeric(group["adjusted_close"], errors="coerce").dropna()
    amount = pd.to_numeric(group["amount"], errors="coerce").dropna()
    last = float(close.iloc[-1]) if len(close) else None

    def change(days: int) -> float | None:
        if len(close) <= days or not close.iloc[-days - 1]:
            return None
        return float(close.iloc[-1] / close.iloc[-days - 1] - 1)

    tail = close.tail(61).pct_change(fill_method=None).dropna()
    year = close.tail(250)
    return {
        "ret_20d": change(20),
        "ret_60d": change(60),
        "volatility_60d": float(tail.std() * sqrt(244)) if len(tail) >= 20 else None,
        "ma60_gap": last / float(close.tail(60).mean()) - 1 if last and len(close) >= 60 else None,
        "from_high": last / float(year.max()) - 1 if last and len(year) else None,
        "amount_20d": float(amount.tail(20).mean()) if len(amount) else None,
    }


def screen_facts(items: list[dict[str, Any]], history: pd.DataFrame, latest: pd.DataFrame, *, day: date,
                 matched: int, scope: str, conditions: str, ranking: str) -> StockFacts:
    """A facts table for the top ``MAX_STOCKS`` screened stocks (``items`` best first, canonical symbols).

    ``history``: their bars up to ``day``; ``latest``: their bars on ``day`` with ``pe_ttm``, ``pb_mrq``,
    ``turnover_rate`` and ``industry`` attached. Keys are ``<code>.<item>`` for one stock and ``all.<item>``
    for the group, so every point can name what it rests on.
    """

    shown = items[:MAX_STOCKS]
    as_of = day.isoformat()
    by_symbol = {symbol: group.sort_values("trade_date") for symbol, group in history.groupby("symbol", observed=True)}
    today = latest.set_index("symbol") if not latest.empty else pd.DataFrame()
    facts: list[Fact] = []
    values: dict[str, list[float]] = {"pe_ttm": [], "pb_mrq": [], "ret_20d": [], "volatility_60d": []}
    industries: dict[str, int] = {}
    where = "股票池" if scope == "pool" else "全市场"
    for rank, item in enumerate(shown, start=1):
        symbol = item["symbol"]
        code = symbol.split(".")[0]
        name = item.get("name") or code
        group = by_symbol.get(symbol)
        metrics = _metrics(group) if group is not None and not group.empty else {}
        row = today.loc[symbol] if symbol in today.index else None
        pe = _number(row.get("pe_ttm")) if row is not None else None
        pb = _number(row.get("pb_mrq")) if row is not None else None
        turnover = _number(row.get("turnover_rate")) if row is not None else None
        industry = _industry_name(row.get("industry") if row is not None else None)
        if industry:
            industries[industry] = industries.get(industry, 0) + 1
        for key, value in (("pe_ttm", pe), ("pb_mrq", pb), ("ret_20d", metrics.get("ret_20d")), ("volatility_60d", metrics.get("volatility_60d"))):
            if value is not None:
                values[key].append(value)
        rows = [
            ("rank", "排序名次", f"第 {rank} 名（按{ranking}）", rank),
            ("industry", "行业", industry or "本地没有行业分类", None),
            ("close", "收盘价", f"{item['close']:.2f} 元" if item.get("close") is not None else "—", item.get("close")),
            ("change", "当日涨跌幅", _percent(item.get("change")), item.get("change")),
            ("ret_20d", "近 20 个交易日涨跌幅", _percent(metrics.get("ret_20d")), metrics.get("ret_20d")),
            ("ret_60d", "近 60 个交易日涨跌幅", _percent(metrics.get("ret_60d")), metrics.get("ret_60d")),
            ("ma60_gap", "收盘价相对 60 日均线", _percent(metrics.get("ma60_gap")), metrics.get("ma60_gap")),
            ("from_high", "距近一年最高价", _percent(metrics.get("from_high")), metrics.get("from_high")),
            ("volatility_60d", "近 60 日年化波动率", f"{metrics['volatility_60d'] * 100:.1f}%" if metrics.get("volatility_60d") is not None else "—", metrics.get("volatility_60d")),
            ("amount_20d", "近 20 日平均成交额", _amount(metrics.get("amount_20d")), metrics.get("amount_20d")),
            ("turnover", "当日换手率", f"{turnover:.2f}%" if turnover is not None else "—", turnover),
            ("pe_ttm", "市盈率（TTM）", f"{pe:.1f}" if pe is not None else "本地没有", pe),
            ("pb_mrq", "市净率", f"{pb:.2f}" if pb is not None else "本地没有", pb),
        ]
        facts += [Fact(f"{code}.{key}", f"{name}（{code}）", f"{name} {label}", text, value, as_of) for key, label, text, value in rows]

    def mid(key: str, digits: int, percent: bool = False) -> str:
        found = values[key]
        if not found:
            return "本地没有"
        low, middle, high = min(found), median(found), max(found)
        if percent:
            return f"中位数 {middle * 100:+.2f}%，最低 {low * 100:+.2f}%，最高 {high * 100:+.2f}%（{len(found)} 只有数据）"
        return f"中位数 {middle:.{digits}f}，最低 {low:.{digits}f}，最高 {high:.{digits}f}（{len(found)} 只有数据）"

    top_industries = sorted(industries.items(), key=lambda pair: (-pair[1], pair[0]))
    industry_text = "、".join(f"{name} {count} 只" for name, count in top_industries[:8]) or "本地没有行业分类"
    if len(top_industries) > 8:
        industry_text += f"，另有 {len(top_industries) - 8} 个行业各少量"
    group_rows = [
        ("conditions", "筛选条件", f"{conditions}；{ranking}"),
        ("matched", "符合条件的股票", f"{where}里共 {matched} 只符合条件"),
        ("shown", "这次解读的股票", f"排序前 {len(shown)} 只"),
        ("industry", "行业分布（前 {0} 只）".format(len(shown)), industry_text),
        ("pe_ttm", "市盈率（TTM）分布", mid("pe_ttm", 1)),
        ("pb_mrq", "市净率分布", mid("pb_mrq", 2)),
        ("ret_20d", "近 20 个交易日涨跌幅分布", mid("ret_20d", 2, percent=True)),
        ("volatility_60d", "近 60 日年化波动率分布", mid("volatility_60d", 1, percent=True).replace("+", "")),
    ]
    facts = [Fact(f"all.{key}", "整组", label, text, None, as_of) for key, label, text in group_rows] + facts
    return StockFacts("SCREEN", "条件选股结果", day, facts)


def screen_messages(stock: StockFacts) -> list[dict[str, str]]:
    lines = [f"条件选股结果，数据截至 {stock.trade_date}。", "数据表（编号 | 项目 | 数值 | 日期）："]
    lines += [f"{fact.key} | {fact.label} | {fact.text} | {fact.as_of}" for fact in stock.facts]
    return [{"role": "system", "content": SCREEN_SYSTEM}, {"role": "user", "content": "\n".join(lines) + "\n\n请按要求输出 JSON。"}]


def _counts_allowed(text: str, shown: int) -> str:
    """“有 5 只”这类只数不在数据表里：只数不超过解读的只数时从数字检查里拿掉。"""

    import re

    return re.sub(r"(\d+)\s*只", lambda found: "只" if int(found.group(1)) <= shown else found.group(0), text)


def check_screen_brief(data: dict[str, Any], stock: StockFacts) -> dict[str, Any]:
    """The answer as shown: points that pass the checks, each with the local facts it cites."""

    if not isinstance(data, dict) or not any(isinstance(data.get(name), list) for name in SECTIONS):
        raise BriefFormatError("没有找到要点列表")
    facts = stock.by_key()
    shown = sum(1 for fact in stock.facts if fact.key.endswith(".rank"))
    removed = 0
    sections: dict[str, list[dict[str, Any]]] = {}
    for name, limit in SECTIONS.items():
        kept: list[dict[str, Any]] = []
        for item in data.get(name) if isinstance(data.get(name), list) else []:
            if not isinstance(item, dict):
                removed += 1
                continue
            text = str(item.get("text", "")).strip()[:MAX_POINT_CHARS]
            keys = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            cited = [facts[key] for key in dict.fromkeys(str(key).strip() for key in keys) if key in facts][:MAX_EVIDENCE]
            sources = [f"{fact.label} {fact.text} {fact.as_of}" for fact in cited]
            if (not text or not cited or _gives_orders(text) or len(kept) >= limit
                    or not _numbers_supported(_counts_allowed(text, shown), sources)):
                removed += 1
                continue
            kept.append({"text": text, "evidence": [fact.to_dict() for fact in cited]})
        sections[name] = kept
    summary = str(data.get("summary", "")).strip()[:MAX_SUMMARY_CHARS]
    every = [f"{fact.label} {fact.text} {fact.as_of}" for fact in stock.facts]
    if summary and (_gives_orders(summary) or not _numbers_supported(_counts_allowed(summary, shown), every)):
        summary = ""
        removed += 1
    return {"summary": summary, **sections, "removed": removed}
