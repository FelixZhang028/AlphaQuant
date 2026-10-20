"""AI Q&A: answer a free question from the platform's own local data.

The text model cannot call tools, so a question takes two calls:

1. **Plan.** The model reads the question (and what the user is looking at) and answers with a
   JSON list of lookups from a fixed menu: one stock's data, its financial reports, a ranking,
   a comparison, the user's backtests, the factor library, what data the platform has.
2. **Answer.** The backend runs those lookups on local data only and gives the model the
   resulting tables; the model answers from them and says what is missing.

The tables are kept with the answer, so the page shows exactly what the answer rests on. An
answer that gives trading instructions is replaced by a fixed refusal, as in the follow-ups.
"""

from __future__ import annotations

from typing import Any

from quant_platform.ai_research.brief import REFUSAL, BriefFormatError, check_answer, parse_json
from quant_platform.ai_research.screen import METRICS, SCOPES

MAX_LOOKUPS = 4
MAX_STOCK_LOOKUPS = 3          # 单只股票的数据每次要读一年的全市场行情，最多查 3 只
MAX_COMPARE = 6
MAX_HISTORY = 4
MAX_ANSWER_CHARS = 1200
KINDS = ("stock", "financials", "rank", "compare", "backtests", "backtest", "factors", "data_status")

_METRIC_MENU = "、".join(f"{key}（{label}）" for key, (label, _, _) in METRICS.items())
_SCOPE_MENU = "、".join(f"{key}（{label}）" for key, (_, label) in SCOPES.items())

PLAN_SYSTEM = f"""你是 A 股研究平台的助手。平台只能使用本地数据回答问题。你现在的任务不是回答，而是决定要查哪些本地数据。

可以用的查询（type 和参数）：
- stock：一只股票最近一个交易日的数据（价格走势、成交、估值、最新财报摘要、行业、所属指数、分红）。参数 symbol（6 位代码或股票名称）。
- financials：一只股票的历期财报（营收、净利润、同比、毛利率、净利率、净资产收益率、负债率）。参数 symbol。
- rank：按一个指标给股票排序。参数 metric、order（high 从高到低 / low 从低到高）、scope（all 全市场，或 {_SCOPE_MENU}）、
  industry（行业关键词，如“银行”“白酒”“半导体”，可省略）、industry_of（和这只股票同行业，填代码，可省略）、limit（1～20，默认 10）。
  metric 只能是：{_METRIC_MENU}。
- compare：几只股票（2～{MAX_COMPARE} 只）在同一天的指标并排比较。参数 symbols（代码或名称的列表）、metrics（上面的 metric 列表，可省略）。
- backtests：用户自己最近的回测记录列表。没有参数。
- backtest：用户自己的一次回测的详细结果（收益、回撤发生在哪段时间、最好和最差的月份、交易成本）。参数 id（回测编号，或 "latest" 表示最近一次）。
- factors：平台因子库里的因子说明。参数 keyword（如“动量”“市净率”）。
- data_status：平台有哪些数据、从哪天到哪天、各类数据的覆盖情况。没有参数。

规则：
1. 最多 {MAX_LOOKUPS} 个查询，其中 stock 和 financials 加起来最多 {MAX_STOCK_LOOKUPS} 个。比较多只股票时用 compare。
2. 用户说“这只”“它”“这次回测”时，指的是下面“用户正在看”的内容。
3. 纯概念问题（例如“什么是市净率”）或和投资、平台无关的问题，lookups 为空列表。
4. 只输出一个 JSON 对象，不要输出别的文字：{{"lookups": [{{"type": "...", ...}}]}}"""

ANSWER_SYSTEM = """你是 A 股研究平台的助手，帮助普通投资者看懂平台的本地数据。
规则：
1. 关于具体股票、回测、数据覆盖的数字，只能使用“查到的数据”里的内容，照抄表里的写法，不要自己计算新数字，也不要使用你自己记得的数字。
2. 查到的数据里没有的信息（新闻、公司业务、政策、宏观、未来走势），直接说平台的数据里没有，不要猜。
3. 可以用通俗的话解释概念（例如市盈率是什么意思），但不要借机评论具体公司。
4. 不给交易建议：不要出现买入、卖出、加仓、减仓、仓位、目标价、止损这类词，也不要说“值得投资”“推荐”。排序结果只说明按指标排在前面。
5. 和投资、平台无关的问题，礼貌说明你只回答平台数据和投资知识相关的问题。
6. 用简短、平实的中文，不超过 300 字。不要用 Markdown 表格，页面上会单独显示查到的数据表；可以分几行或用“- ”列几点。"""

NO_DATA = "（这个问题没有查本地数据。）"


def context_text(context: dict[str, Any] | None) -> str:
    """What the user is looking at, for both prompts; empty when nothing is known."""

    if not context:
        return ""
    parts = []
    if context.get("page"):
        parts.append(f"页面：{context['page']}")
    if context.get("stock"):
        parts.append(f"正在看的股票：{context['stock']}")
    if context.get("backtest"):
        parts.append(f"正在看的回测：编号 {context['backtest']}")
    return "用户正在看：" + "；".join(parts) if parts else ""


def _history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    messages = []
    for turn in history[-MAX_HISTORY:]:
        messages += [{"role": "user", "content": str(turn.get("question", ""))},
                     {"role": "assistant", "content": str(turn.get("answer", ""))}]
    return messages


def plan_messages(question: str, history: list[dict[str, Any]], context: str = "") -> list[dict[str, str]]:
    asked = f"{context}\n\n用户的问题：{question}" if context else f"用户的问题：{question}"
    return [{"role": "system", "content": PLAN_SYSTEM}, *_history(history),
            {"role": "user", "content": asked + "\n\n请只输出要查询的 JSON。"}]


def _text(value: Any, limit: int = 40) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def parse_plan(text: str) -> list[dict[str, Any]]:
    """The lookups the model asked for, cleaned and capped; unknown kinds and bad parameters are dropped."""

    try:
        data = parse_json(text)
    except BriefFormatError:
        return []
    items = data.get("lookups") if isinstance(data.get("lookups"), list) else []
    lookups, stocks = [], 0
    for item in items:
        if not isinstance(item, dict) or item.get("type") not in KINDS or len(lookups) >= MAX_LOOKUPS:
            continue
        kind = item["type"]
        if kind in ("stock", "financials"):
            if stocks >= MAX_STOCK_LOOKUPS or not _text(item.get("symbol")):
                continue
            stocks += 1
            lookups.append({"type": kind, "symbol": _text(item["symbol"], 20)})
        elif kind == "rank":
            if item.get("metric") not in METRICS:
                continue
            try:
                limit = max(1, min(20, int(item.get("limit") or 10)))
            except (TypeError, ValueError):
                limit = 10
            lookups.append({"type": "rank", "metric": item["metric"], "order": "low" if item.get("order") == "low" else "high",
                            "scope": item.get("scope") if item.get("scope") in SCOPES else "all",
                            "industry": _text(item.get("industry"), 20), "industry_of": _text(item.get("industry_of"), 20),
                            "limit": limit})
        elif kind == "compare":
            symbols = [_text(s, 20) for s in item.get("symbols") or [] if _text(s, 20)][:MAX_COMPARE] if isinstance(item.get("symbols"), list) else []
            metrics = [m for m in item.get("metrics") or [] if m in METRICS] if isinstance(item.get("metrics"), list) else []
            if len(symbols) >= 2:
                lookups.append({"type": "compare", "symbols": symbols, "metrics": metrics})
        elif kind == "backtest":
            lookups.append({"type": "backtest", "id": _text(item.get("id") or "latest", 12)})
        elif kind == "factors":
            if _text(item.get("keyword")):
                lookups.append({"type": "factors", "keyword": _text(item["keyword"], 20)})
        else:
            lookups.append({"type": kind})
    # 同一个查询只做一次。
    unique: dict[str, dict[str, Any]] = {}
    for lookup in lookups:
        unique.setdefault(repr(sorted(lookup.items())), lookup)
    return list(unique.values())


def render_block(block: dict[str, Any]) -> str:
    """One data block as text for the model."""

    lines = [f"【{block.get('title', '')}】数据截至 {block.get('as_of') or '—'}"]
    if block.get("error"):
        lines.append(f"没有查到：{block['error']}")
    if block.get("columns"):
        lines.append(" | ".join(block["columns"]))
        lines += [" | ".join(str(cell) for cell in row) for row in block.get("rows", [])]
    lines += [f"说明：{note}" for note in block.get("notes", [])]
    return "\n".join(lines)


def answer_messages(question: str, history: list[dict[str, Any]], blocks: list[dict[str, Any]], context: str = "") -> list[dict[str, str]]:
    data = "\n\n".join(render_block(block) for block in blocks) if blocks else NO_DATA
    asked = (f"{context}\n\n" if context else "") + f"查到的数据：\n{data}\n\n用户的问题：{question}"
    return [{"role": "system", "content": ANSWER_SYSTEM}, *_history(history), {"role": "user", "content": asked}]


def checked_answer(text: str) -> str:
    """The answer as shown: trimmed, and replaced by the refusal when it gives trading instructions."""

    answer = check_answer(text)
    return answer if answer == REFUSAL else answer[:MAX_ANSWER_CHARS]
