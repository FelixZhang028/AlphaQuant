"""Readable stock reports from typed Jev answers and saved facts, without a text LLM.

Explanations are explicitly authored templates, not a model's hidden reasoning.
Missing dimensions are never sent to the model or filled with invented judgements.
"""
from __future__ import annotations

from typing import Any

from .decisions import RISK_LEVELS, TILT_QUESTION, model_name, stock_state
from .facts import StockFacts
from quant_platform.jev import choice_question, score_question

REPORT_VERSION = 2
MISSING_EXPLANATIONS = {
    "trend": "区间涨跌幅和均线数据不足，暂时无法判断趋势。",
    "trading": "缺少近期平均成交额或相对成交水平，暂时无法判断成交配合。",
    "volatility": "缺少可用的波动率或历史回撤，暂时无法判断这一维度。",
    "valuation": "缺少自身历史或同行业估值对照，暂时不能仅凭绝对估值判断高低。",
    "financials": "可用的已公告盈利、增长或负债数据不足，暂时无法判断经营情况。",
}
ASSESSMENTS = {
    "支持": "本维度的数据提供相对有利的线索；不代表可以单独预测上涨",
    "中性": "本维度的信号不突出或相互抵消，没有清晰方向",
    "需留意": "本维度存在需要进一步核查的风险或不利线索",
    "数据不足": "现有输入不足以对本维度作出判断，不得用常识补齐缺失数据",
}
DIMENSIONS = (
    {"key": "trend", "title": "趋势与动能", "description": "价格走势是否同向，是否偏离均线",
     "keys": ("ret_5d", "ret_20d", "ret_60d", "ma20_gap", "ma60_gap", "rsi_14"),
     "instruction": "综合短中期涨跌幅、均线位置与 RSI，判断趋势是否提供支持。上涨和过热信号并存时不要只看涨幅。",
     "meanings": {"支持": "价格与动能线索整体偏有利，仍需观察能否持续。", "中性": "走势信号尚不明确，或短中期表现存在分歧。", "需留意": "走势或动能出现不利线索，需要留意趋势变化。"}},
    {"key": "trading", "title": "成交配合", "description": "成交是否配合走势，交易是否活跃",
     "keys": ("change_1d", "ret_20d", "amount_20d", "amount_ratio", "turnover_rate"),
     "instruction": "根据成交额及其相对近期均值、当日涨跌和换手率判断成交配合。不能仅凭成交额大小推断资金净流入。",
     "meanings": {"支持": "成交线索对当前走势形成一定配合。", "中性": "成交尚未提供明确的方向支持。", "需留意": "成交与走势的配合值得核查，避免把活跃交易直接当作看多信号。"}},
    {"key": "volatility", "title": "波动与回撤", "description": "近期波动及历史回撤是否值得警惕",
     "keys": ("volatility_60d", "max_drawdown_250d", "from_high_250d", "rsi_14", "is_st"),
     "instruction": "根据年化波动率、历史回撤和 ST 状态判断风险线索。支持表示这些线索相对温和，不表示没有风险；不得推算未来亏损概率。",
     "meanings": {"支持": "模型认为已有波动和回撤线索相对温和，仍不等于未来风险低。", "中性": "现有风险线索没有形成鲜明结论。", "需留意": "波动、历史回撤或特殊风险状态值得优先关注。"}},
    {"key": "valuation", "title": "估值位置", "description": "结合自身历史或同行业比较估值",
     "keys": ("pe_ttm", "pe_position", "industry_pe_median", "pb_mrq", "ps_ttm"),
     "instruction": "结合历史市盈率位置或同行业市盈率比较，判断估值线索。负市盈率表示亏损，不能解读成便宜；缺少对照时不要仅用绝对 PE 或 PB 断言高低。",
     "meanings": {"支持": "现有估值对照提供相对有利的线索，不代表价格一定上涨。", "中性": "估值对照没有形成明显优势或不利结论。", "需留意": "估值对照或亏损线索值得留意，需要结合经营数据核查。"}},
    {"key": "financials", "title": "经营与财务", "description": "已公告财报中的盈利、增长与负债",
     "keys": ("report", "roe_avg", "net_margin", "gross_margin", "profit_growth", "debt_ratio"),
     "instruction": "只根据已公告财报，综合盈利、利润增长和负债判断经营线索。不知道的财务指标不能补猜，也不得把历史增长当成未来承诺。",
     "meanings": {"支持": "已公告的经营和财务线索整体偏有利。", "中性": "财务线索尚不突出，或优势与压力并存。", "需留意": "盈利、增长或负债方面存在需要核查的线索。"}},
)


def _evidence(stock: StockFacts, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    known = stock.by_key()
    return [known[key].to_dict() for key in keys if key in known]


def _ready(key: str, stock: StockFacts) -> bool:
    facts = stock.by_key()
    numeric = {name for name, fact in facts.items() if fact.value is not None}
    if key == "trend":
        return len(numeric & {"ret_20d", "ret_60d", "ma20_gap", "ma60_gap"}) >= 2
    if key == "trading":
        return {"amount_20d", "amount_ratio"} <= numeric
    if key == "volatility":
        return bool(numeric & {"volatility_60d", "max_drawdown_250d"})
    if key == "valuation":
        return ("pe_position" in numeric or {"pe_ttm", "industry_pe_median"} <= numeric
                or ("pe_ttm" in numeric and facts["pe_ttm"].value <= 0))
    return len(numeric & {"roe_avg", "net_margin", "gross_margin", "profit_growth", "debt_ratio"}) >= 2


def stock_report(client: Any, stock: StockFacts) -> dict[str, Any]:
    questions = {"tilt": TILT_QUESTION}
    for spec in DIMENSIONS:
        if _ready(spec["key"], stock):
            questions[spec["key"]] = choice_question(
                "只使用 state 中对应维度的已知数据。" + spec["instruction"], ASSESSMENTS)
    # A rating requires actual measured volatility or drawdown, not merely a stock name.
    risk_ready = _ready("volatility", stock)
    if risk_ready:
        questions["risk"] = score_question(
            "只根据已有波动率、历史回撤、过热信号和 ST 状态，对当前可见的风险线索评级。"
            "缺少估值或财务时不得猜测，不要把此评级当成未来亏损概率。", RISK_LEVELS)
    state = stock_state(stock)
    state["数据说明"] = list(stock.notes)
    answers = client.ask(state, questions)
    tilt = answers["tilt"]
    dimensions = []
    for spec in DIMENSIONS:
        answer = answers.get(spec["key"])
        assessment = answer["choice"] if answer else "数据不足"
        evaluated = answer is not None and assessment != "数据不足"
        dimensions.append({
            "key": spec["key"], "title": spec["title"], "description": spec["description"],
            "status": "evaluated" if evaluated else "insufficient", "assessment": assessment,
            "confidence": answer["confidence"] if answer else None,
            "probabilities": answer["probabilities"] if answer else {},
            "interpretation": spec["meanings"].get(assessment,
                "模型认为现有输入仍不足以形成可靠判断，本维度保留结论。" if answer else MISSING_EXPLANATIONS[spec["key"]]),
            "evidence": _evidence(stock, spec["keys"]),
        })
    supports = [item["title"] for item in dimensions if item["assessment"] == "支持"]
    concerns = [item["title"] for item in dimensions if item["assessment"] == "需留意"]
    unavailable = [item["title"] for item in dimensions if item["status"] == "insufficient"]
    risk = answers.get("risk")
    headline = {
        "偏多": "当前数据的综合判断偏多，仍需结合风险与数据缺口理解。",
        "中性": "当前数据的综合判断偏中性，尚未形成明确的方向优势。",
        "偏空": "当前数据的综合判断偏空，优先关注不利线索与风险。",
    }[tilt["choice"]]
    followups = []
    if unavailable:
        followups.append({"title": "补全判断依据", "text": "、".join(unavailable) + "暂无法判断，补齐对应历史、对照或财报后再分析。", "action": "data-update"})
    if supports and concerns:
        followups.append({"title": "核查信号分歧", "text": "有利线索与需留意事项并存，不宜只看综合倾向忽略分项结果。"})
    if tilt["confidence"] < .5:
        followups.append({"title": "保留不确定性", "text": "本次综合判断的模型置信度较低，需要更多证据确认。"})
    followups.append({"title": "跟踪后续变化", "text": "后续行情更新后再新建分析，并在历史记录中对照实际走势。"})
    return {
        "choice": tilt["choice"], "probabilities": tilt["probabilities"], "confidence": tilt["confidence"],
        "model": model_name(client), "report_version": REPORT_VERSION,
        "as_of": stock.trade_date.isoformat(), "summary": headline, "dimensions": dimensions,
        "supports": supports, "concerns": concerns, "followups": followups,
        "coverage": {"evaluated": sum(item["status"] == "evaluated" for item in dimensions),
                     "total": len(dimensions), "unavailable": unavailable, "missing": list(stock.missing), "notes": list(stock.notes)},
        "risk": {"level": RISK_LEVELS[min(len(RISK_LEVELS) - 1, max(0, round(risk["score"])))],
                 "score": risk["score"], "probabilities": risk["probabilities"], "confidence": risk["confidence"]} if risk else None,
    }
