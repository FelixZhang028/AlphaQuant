"""Versioned, auditable schema shared by templates and the visual rule builder."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from math import isfinite
from typing import Any

from quant_platform.core.exceptions import ConfigurationError

SCHEMA_VERSION = 1

INDICATOR_LABELS: dict[str, str] = {
    "close": "收盘价",
    "return": "区间涨跌幅",
    "moving_average": "移动平均线",
    "volatility": "历史波动率",
    "average_amount": "平均成交额",
    "previous_high": "前期最高收盘价",
    "previous_low": "前期最低收盘价",
    "rsi": "RSI强弱指标",
    "drawdown": "区间回撤",
}

OPERATOR_LABELS: dict[str, str] = {
    "greater_than": "大于",
    "greater_or_equal": "大于等于",
    "less_than": "小于",
    "less_or_equal": "小于等于",
}

_WINDOW_RULES: dict[str, tuple[int, int]] = {
    "return": (1, 500),
    "moving_average": (2, 500),
    "volatility": (2, 250),
    "average_amount": (1, 250),
    "previous_high": (2, 500),
    "previous_low": (2, 500),
    "rsi": (2, 120),
    "drawdown": (2, 500),
}


@dataclass(frozen=True)
class IndicatorSpec:
    """One approved point-in-time indicator."""

    name: str
    window: int | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> IndicatorSpec:
        if not isinstance(value, dict):
            raise ConfigurationError("指标必须是对象")
        name = str(value.get("name", "")).strip()
        raw_window = value.get("window")
        window = int(raw_window) if raw_window is not None else None
        result = cls(name=name, window=window)
        result.validate()
        return result

    def validate(self) -> None:
        if self.name not in INDICATOR_LABELS:
            raise ConfigurationError(f"不支持的指标：{self.name}")
        if self.name == "close":
            if self.window is not None:
                raise ConfigurationError("收盘价指标不需要周期")
            return
        if self.window is None:
            raise ConfigurationError(f"{INDICATOR_LABELS[self.name]}必须设置周期")
        minimum, maximum = _WINDOW_RULES[self.name]
        if not minimum <= self.window <= maximum:
            raise ConfigurationError(
                f"{INDICATOR_LABELS[self.name]}周期必须在{minimum}至{maximum}之间"
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"name": self.name}
        if self.window is not None:
            result["window"] = self.window
        return result

    def describe(self) -> str:
        label = INDICATOR_LABELS[self.name]
        return label if self.window is None else f"{self.window}日{label}"


@dataclass(frozen=True)
class RuleSpec:
    """A comparison between an indicator and a constant or another indicator."""

    left: IndicatorSpec
    operator: str
    value: float | None = None
    right: IndicatorSpec | None = None

    @classmethod
    def from_mapping(cls, value: Any) -> RuleSpec:
        if not isinstance(value, dict):
            raise ConfigurationError("条件规则必须是对象")
        raw_value = value.get("value")
        result = cls(
            left=IndicatorSpec.from_mapping(value.get("left")),
            operator=str(value.get("operator", "")).strip(),
            value=float(raw_value) if raw_value is not None else None,
            right=(
                IndicatorSpec.from_mapping(value["right"])
                if value.get("right") is not None
                else None
            ),
        )
        result.validate()
        return result

    def validate(self) -> None:
        self.left.validate()
        if self.operator not in OPERATOR_LABELS:
            raise ConfigurationError(f"不支持的判断方式：{self.operator}")
        if (self.value is None) == (self.right is None):
            raise ConfigurationError("条件右侧必须且只能选择固定值或另一个指标")
        if self.value is not None and not isfinite(self.value):
            raise ConfigurationError("条件固定值必须是有限数字")
        if self.right is not None:
            self.right.validate()

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "left": self.left.to_dict(),
            "operator": self.operator,
        }
        if self.right is not None:
            result["right"] = self.right.to_dict()
        else:
            result["value"] = self.value
        return result

    def describe(self) -> str:
        right = self.right.describe() if self.right is not None else _format_number(self.value)
        return f"{self.left.describe()}{OPERATOR_LABELS[self.operator]}{right}"


@dataclass(frozen=True)
class RankingSpec:
    """Cross-sectional ordering used by the portfolio's top-N selector."""

    indicator: IndicatorSpec
    direction: str = "descending"

    @classmethod
    def from_mapping(cls, value: Any) -> RankingSpec:
        if not isinstance(value, dict):
            raise ConfigurationError("排序规则必须是对象")
        result = cls(
            indicator=IndicatorSpec.from_mapping(value.get("indicator")),
            direction=str(value.get("direction", "descending")),
        )
        result.validate()
        return result

    def validate(self) -> None:
        self.indicator.validate()
        if self.direction not in {"ascending", "descending"}:
            raise ConfigurationError("排序方向只能是ascending或descending")

    def to_dict(self) -> dict[str, Any]:
        return {"indicator": self.indicator.to_dict(), "direction": self.direction}

    def describe(self) -> str:
        direction = "从高到低" if self.direction == "descending" else "从低到高"
        return f"按{self.indicator.describe()}{direction}排序"


@dataclass(frozen=True)
class RuleStrategyDefinition:
    """Portable strategy definition generated by P0 templates or P1 blocks."""

    strategy_id: str
    name: str
    description: str
    entry_logic: str
    entry_rules: tuple[RuleSpec, ...]
    ranking: RankingSpec
    schema_version: int = SCHEMA_VERSION

    @classmethod
    def from_mapping(cls, value: Any) -> RuleStrategyDefinition:
        if not isinstance(value, dict):
            raise ConfigurationError("策略配置必须是对象")
        raw_rules = value.get("entry_rules", [])
        if not isinstance(raw_rules, list):
            raise ConfigurationError("买入条件必须是列表")
        result = cls(
            strategy_id=str(value.get("strategy_id", "")).strip(),
            name=str(value.get("name", "")).strip(),
            description=str(value.get("description", "")).strip(),
            entry_logic=str(value.get("entry_logic", "all")).strip(),
            entry_rules=tuple(RuleSpec.from_mapping(item) for item in raw_rules),
            ranking=RankingSpec.from_mapping(value.get("ranking")),
            schema_version=int(value.get("schema_version", SCHEMA_VERSION)),
        )
        result.validate()
        return result

    @classmethod
    def from_json(cls, text: str) -> RuleStrategyDefinition:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"策略JSON格式错误：{exc}") from exc
        return cls.from_mapping(value)

    def validate(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ConfigurationError(f"不支持的策略协议版本：{self.schema_version}")
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", self.strategy_id):
            raise ConfigurationError("策略编号只能包含字母、数字、下划线和连字符")
        if not self.name or len(self.name) > 80:
            raise ConfigurationError("策略名称不能为空且不能超过80个字符")
        if self.entry_logic not in {"all", "any"}:
            raise ConfigurationError("条件组合只能是all或any")
        if not 1 <= len(self.entry_rules) <= 10:
            raise ConfigurationError("策略必须包含1至10条买入条件")
        for rule in self.entry_rules:
            rule.validate()
        self.ranking.validate()

    @property
    def minimum_history_days(self) -> int:
        indicators = [self.ranking.indicator]
        for rule in self.entry_rules:
            indicators.append(rule.left)
            if rule.right is not None:
                indicators.append(rule.right)
        requirements = [_indicator_history(item) for item in indicators]
        return max(requirements, default=1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "entry_logic": self.entry_logic,
            "entry_rules": [rule.to_dict() for rule in self.entry_rules],
            "ranking": self.ranking.to_dict(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    def describe(self, *, top_n: int, rebalance: str) -> str:
        logic = "并且" if self.entry_logic == "all" else "或者"
        conditions = f"，{logic}".join(rule.describe() for rule in self.entry_rules)
        frequencies = {"daily": "每日", "weekly": "每周", "monthly": "每月"}
        return (
            f"{frequencies.get(rebalance, rebalance)}调仓；只保留满足“{conditions}”的股票；"
            f"{self.ranking.describe()}，等权持有前{top_n}只。条件失效时在下一次调仓退出。"
        )


def _indicator_history(indicator: IndicatorSpec) -> int:
    if indicator.window is None:
        return 1
    needs_previous = {
        "return",
        "volatility",
        "previous_high",
        "previous_low",
        "rsi",
    }
    return indicator.window + 1 if indicator.name in needs_previous else indicator.window


def _format_number(value: float | None) -> str:
    if value is None:
        return "未知值"
    if 0 < abs(value) < 1:
        return f"{value:.2%}"
    return f"{value:,.2f}"
