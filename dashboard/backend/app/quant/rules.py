"""零代码策略定义桥：前端词汇 <-> quant_platform rule_schema。

前端的指标/算子命名（return_1d、gt 等）与 AlphaQuant 规则 schema
（return、greater_than 等）结构一致但词汇不同；本模块负责双向翻译，
并把前端缺省的指标周期补成默认值，使现有 UI 无需改动即可对接真实引擎。
"""

from __future__ import annotations

from typing import Any

from quant_platform.strategies.rule_schema import RuleStrategyDefinition

# 前端指标名 -> (quant 指标名, 默认周期)；close 无周期。
INDICATOR_TO_QUANT: dict[str, tuple[str, int | None]] = {
    "close": ("close", None),
    "return_1d": ("return", 20),
    "sma": ("moving_average", 20),
    "volatility": ("volatility", 20),
    "amount_ma": ("average_amount", 20),
    "high_max": ("previous_high", 20),
    "low_min": ("previous_low", 20),
    "rsi": ("rsi", 14),
    "drawdown": ("drawdown", 20),
}

OPERATOR_TO_QUANT: dict[str, str] = {
    "gt": "greater_than",
    "gte": "greater_or_equal",
    "lt": "less_than",
    "lte": "less_or_equal",
}

QUANT_TO_INDICATOR: dict[str, str] = {
    quant: frontend for frontend, (quant, _) in INDICATOR_TO_QUANT.items()
}
QUANT_TO_OPERATOR: dict[str, str] = {quant: frontend for frontend, quant in OPERATOR_TO_QUANT.items()}


def _indicator_to_quant(spec: dict[str, Any]) -> dict[str, Any]:
    name = str(spec.get("name", "")).strip()
    mapped = INDICATOR_TO_QUANT.get(name)
    if mapped is not None:
        quant_name, default_window = mapped
        window = spec.get("window")
        result: dict[str, Any] = {"name": quant_name}
        if default_window is not None:
            result["window"] = int(window) if window is not None else default_window
        return result
    return {"name": name, **({"window": int(spec["window"])} if spec.get("window") is not None else {})}


def _indicator_to_frontend(spec: dict[str, Any]) -> dict[str, Any]:
    name = str(spec.get("name", "")).strip()
    result: dict[str, Any] = {"name": QUANT_TO_INDICATOR.get(name, name)}
    if spec.get("window") is not None:
        result["window"] = int(spec["window"])
    return result


def definition_to_quant(definition: dict[str, Any]) -> dict[str, Any]:
    """前端策略定义 -> quant_platform 规则定义（可交给 from_mapping 校验）。"""

    rules: list[dict[str, Any]] = []
    for rule in definition.get("entry_rules") or []:
        translated: dict[str, Any] = {
            "left": _indicator_to_quant(rule.get("left") or {}),
            "operator": OPERATOR_TO_QUANT.get(
                str(rule.get("operator", "")), str(rule.get("operator", ""))
            ),
        }
        if rule.get("value") is not None:
            translated["value"] = float(rule["value"])
        elif rule.get("right") is not None:
            translated["right"] = _indicator_to_quant(rule["right"])
        rules.append(translated)
    if not rules:
        # 规则引擎要求 1~10 条：空条件（模板快速回测场景）补一条恒真规则。
        rules.append({"left": {"name": "close"}, "operator": "greater_than", "value": 0.0})

    ranking = definition.get("ranking") or {}
    return {
        "schema_version": 1,
        "strategy_id": str(definition.get("strategy_id") or "").strip(),
        "name": str(definition.get("name") or "").strip(),
        "description": str(definition.get("description") or ""),
        "entry_logic": str(definition.get("entry_logic") or "all"),
        "entry_rules": rules,
        "ranking": {
            "indicator": _indicator_to_quant(ranking.get("indicator") or {}),
            "direction": str(ranking.get("direction") or "descending"),
        },
    }


def definition_to_frontend(definition: dict[str, Any]) -> dict[str, Any]:
    """quant_platform 规则定义 -> 前端策略定义（列表/详情返回用）。"""

    rules = []
    for rule in definition.get("entry_rules") or []:
        translated = {
            "left": _indicator_to_frontend(rule.get("left") or {}),
            "operator": QUANT_TO_OPERATOR.get(
                str(rule.get("operator", "")), str(rule.get("operator", ""))
            ),
        }
        if rule.get("value") is not None:
            translated["value"] = rule["value"]
        elif rule.get("right") is not None:
            translated["right"] = _indicator_to_frontend(rule["right"])
        rules.append(translated)
    ranking = definition.get("ranking") or {}
    return {
        "schema_version": definition.get("schema_version", 1),
        "strategy_id": definition.get("strategy_id", ""),
        "name": definition.get("name", ""),
        "description": definition.get("description", ""),
        "entry_logic": definition.get("entry_logic", "all"),
        "entry_rules": rules,
        "ranking": {
            "indicator": _indicator_to_frontend(ranking.get("indicator") or {}),
            "direction": ranking.get("direction", "descending"),
        },
    }


def parse_definition(definition: dict[str, Any]) -> RuleStrategyDefinition:
    """前端定义 -> 校验后的 RuleStrategyDefinition（校验失败抛 ConfigurationError）。"""

    return RuleStrategyDefinition.from_mapping(definition_to_quant(definition))
