"""The AI reading of one stock's facts, and the checks it has to pass before anyone sees it.

The model gets the facts table and nothing else. It answers with a lean (偏多 / 中性 / 偏空), a
short summary and three lists of points; each point names the facts it rests on. A point is
dropped when it names no known fact, when one of its numbers is not in the facts it names, or
when it gives trading instructions (买入, 目标价 ...). The page shows the facts next to each
point from the local data, not the model's retelling of them.
"""

from __future__ import annotations

import json
import re
from typing import Any

from quant_platform.ai_research.facts import StockFacts

TILTS = ("偏多", "中性", "偏空")
CONFIDENCE = ("高", "中", "低")
SECTIONS = {"bull_points": 4, "risk_points": 4, "watch_points": 3}
MAX_EVIDENCE = 3
MAX_POINT_CHARS = 120
MAX_SUMMARY_CHARS = 200
# 出现这些词就是在给交易指令，平台不提供。
TRADING_WORDS = ("买入", "卖出", "加仓", "减仓", "建仓", "清仓", "满仓", "抄底", "仓位", "目标价", "止损", "止盈")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")

RULES = """规则：
1. 只能使用“数据表”里的内容。表里没有的信息（新闻、公司业务、行业政策、宏观、财报细节）一律不写，也不要猜。
2. 引用数字时照抄数据表里的写法，不要自己计算新的数字。
3. 不给交易建议：不要出现买入、卖出、加仓、减仓、仓位、目标价、止损这类词。整体倾向只填在 tilt 里（偏多、中性或偏空）；
   summary 和要点里不要用“偏多、偏空、看多、看空”这类词，用“利好因素”“风险因素”来描述数据。
4. 用简短、平实的中文。
5. “研究经验”是用户自己的看法，可以帮助决定关注什么，但不能当作数据依据。"""

BRIEF_SYSTEM = f"""你是 A 股研究助手，帮助普通投资者读懂一只股票的数据。
{RULES}
6. 每条要点在 evidence 里写出它依据的数据编号（1～3 个，只能用数据表第一列里的编号），每条不超过 60 个字。

只输出一个 JSON 对象，不要输出别的文字：
{{"tilt": "偏多、中性或偏空", "confidence": "高、中或低", "summary": "一到两句话的总体看法，不超过 100 字",
"bull_points": [{{"text": "数据里的一条利好因素", "evidence": ["数据编号"]}}],
"risk_points": [{{"text": "数据里的一条风险因素", "evidence": ["数据编号"]}}],
"watch_points": [{{"text": "接下来值得留意的一件事", "evidence": ["数据编号"]}}]}}
bull_points 和 risk_points 各 1～4 条，watch_points 0～3 条。数据不够时信心写“低”。"""

ASK_SYSTEM = f"""你是 A 股研究助手。用户已经看过这只股票的数据和你之前的解读，现在继续提问。
{RULES}
6. 问题需要的数据不在表里时，直接说“本地数据里没有这一项”，并说明可以在「数据更新」里下载哪类数据。
7. 回答不超过 200 字。"""

REFUSAL = "这个问题涉及买卖建议，平台不提供。可以问我数据里的具体内容，例如估值、走势或风险。"


class BriefFormatError(ValueError):
    """The model's answer is not the JSON object asked for."""


def facts_table(stock: StockFacts) -> str:
    lines = [f"股票：{stock.name}（{stock.symbol}），数据截至 {stock.trade_date}。", "数据表（编号 | 项目 | 数值 | 日期）："]
    lines += [f"{fact.key} | {fact.label} | {fact.text} | {fact.as_of}" for fact in stock.facts]
    if stock.missing:
        lines.append("本地缺少的数据（不要猜测这些内容）：")
        lines += [f"- {item['group']}：{item['reason']}" for item in stock.missing]
    lines += [f"说明：{note}" for note in stock.notes]
    return "\n".join(lines)


def _experience_block(experience: str) -> str:
    return f"\n\n研究经验（用户自己的看法，不是数据）：\n{experience.strip()}" if experience.strip() else ""


def brief_messages(stock: StockFacts, experience: str = "") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": BRIEF_SYSTEM},
        {"role": "user", "content": facts_table(stock) + _experience_block(experience) + "\n\n请按要求输出 JSON。"},
    ]


def retry_messages(messages: list[dict[str, str]], answer: str, problem: str) -> list[dict[str, str]]:
    return [*messages, {"role": "assistant", "content": answer},
            {"role": "user", "content": f"上面的输出无法使用：{problem}。请重新只输出一个符合要求的 JSON 对象。"}]


def parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise BriefFormatError("没有找到 JSON 对象")
    try:
        data = json.loads(cleaned[start:end + 1])
    except json.JSONDecodeError as exc:
        raise BriefFormatError(f"JSON 格式不对（{exc.msg}）") from exc
    if not isinstance(data, dict):
        raise BriefFormatError("输出不是 JSON 对象")
    return data


def _numbers_supported(text: str, sources: list[str]) -> bool:
    """Every number in ``text`` appears in ``sources``, allowing for rounding to the digits written."""

    allowed = [float(found) for source in sources for found in _NUMBER.findall(source.replace(",", ""))]
    for found in _NUMBER.findall(text.replace(",", "")):
        decimals = len(found.split(".")[1]) if "." in found else 0
        tolerance = 0.5 * 10 ** -decimals + 1e-9
        if not any(abs(float(found) - value) <= tolerance for value in allowed):
            return False
    return True


def _gives_orders(text: str) -> bool:
    return any(word in text for word in TRADING_WORDS)


def check_brief(data: dict[str, Any], stock: StockFacts) -> dict[str, Any]:
    """The answer as shown: points that pass the checks, each with the local facts it cites.

    Raises :class:`BriefFormatError` when the lean is missing or unknown, so the caller can ask once more.
    """

    tilt = str(data.get("tilt", "")).strip()
    if tilt not in TILTS:
        raise BriefFormatError("tilt 必须是 偏多、中性 或 偏空")
    confidence = str(data.get("confidence", "")).strip()
    confidence = confidence if confidence in CONFIDENCE else "低"
    facts = stock.by_key()
    removed = 0
    sections: dict[str, list[dict[str, Any]]] = {}
    for name, limit in SECTIONS.items():
        kept: list[dict[str, Any]] = []
        items = data.get(name) if isinstance(data.get(name), list) else []
        for item in items:
            if not isinstance(item, dict):
                removed += 1
                continue
            text = str(item.get("text", "")).strip()[:MAX_POINT_CHARS]
            keys = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            cited = [facts[key] for key in dict.fromkeys(str(key).strip() for key in keys) if key in facts][:MAX_EVIDENCE]
            sources = [f"{fact.label} {fact.text} {fact.as_of}" for fact in cited]
            if not text or not cited or _gives_orders(text) or not _numbers_supported(text, sources) or len(kept) >= limit:
                removed += 1
                continue
            kept.append({"text": text, "evidence": [fact.to_dict() for fact in cited]})
        sections[name] = kept
    summary = str(data.get("summary", "")).strip()[:MAX_SUMMARY_CHARS]
    every = [f"{fact.label} {fact.text} {fact.as_of}" for fact in stock.facts]
    if summary and (_gives_orders(summary) or not _numbers_supported(summary, every)):
        summary = ""
        removed += 1
    return {"tilt": tilt, "confidence": confidence, "summary": summary, **sections, "removed": removed}


def ask_messages(stock: StockFacts, brief: dict[str, Any] | None, history: list[dict[str, str]],
                 question: str, experience: str = "") -> list[dict[str, str]]:
    context = facts_table(stock) + _experience_block(experience)
    if brief:
        points = [f"- {point['text']}" for name in SECTIONS for point in brief.get(name, [])]
        context += f"\n\n你之前的解读：倾向{brief['tilt']}，信心{brief['confidence']}。{brief.get('summary', '')}\n" + "\n".join(points)
    messages = [{"role": "system", "content": ASK_SYSTEM}, {"role": "user", "content": context},
                {"role": "assistant", "content": "好的，我已经看过这些数据，请提问。"}]
    for turn in history:
        messages += [{"role": "user", "content": turn["question"]}, {"role": "assistant", "content": turn["answer"]}]
    return [*messages, {"role": "user", "content": question}]


def check_answer(text: str) -> str:
    answer = text.strip()
    return REFUSAL if not answer or _gives_orders(answer) else answer
