"""Safe generic strategy interpreter for versioned visual-builder definitions."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, ClassVar

import pandas as pd

from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.rule_schema import (
    IndicatorSpec,
    RuleSpec,
    RuleStrategyDefinition,
)
from quant_platform.strategies.spec import ParameterKind, StrategyParameter

_TRADING_DAYS = 244


@dataclass(frozen=True)
class RuleBasedParameters:
    definition: RuleStrategyDefinition


class RuleBasedStrategy(Strategy):
    """Evaluate approved indicators without executing user-supplied program code."""

    plugin_name = "rule_builder"
    display_name = "零代码规则策略"
    description = "由模板或积木编辑器生成，使用白名单指标和判断条件"
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "definition_json",
            "结构化策略规则",
            ParameterKind.STRING,
            "{}",
            "平台生成的版本化规则；普通用户无需直接编辑",
        ),
    )
    required_fields = frozenset({"symbol", "trade_date", "adjusted_close", "amount"})

    def __init__(self, strategy_id: str, parameters: RuleBasedParameters) -> None:
        self.strategy_id = strategy_id
        self.config = parameters

    @classmethod
    def from_parameters(
        cls, strategy_id: str, parameters: dict[str, Any]
    ) -> RuleBasedStrategy:
        definition = RuleStrategyDefinition.from_json(str(parameters["definition_json"]))
        return cls(strategy_id, RuleBasedParameters(definition))

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        context.require_fields(self.required_fields)
        definition = self.config.definition
        history = context.history(
            fields=["adjusted_close", "amount"],
            lookback=definition.minimum_history_days,
        )
        cutoff = pd.Timestamp(context.trade_date)
        signals: list[Signal] = []
        for symbol, original in history.groupby("symbol", observed=True):
            group = original.sort_values("trade_date").copy()
            if group.empty or pd.Timestamp(group.iloc[-1]["trade_date"]) != cutoff:
                continue
            group[["adjusted_close", "amount"]] = group[
                ["adjusted_close", "amount"]
            ].apply(pd.to_numeric, errors="coerce")
            outcomes = [_evaluate_rule(group, rule) for rule in definition.entry_rules]
            eligible = all(outcomes) if definition.entry_logic == "all" else any(outcomes)
            if not eligible:
                continue
            score = _indicator_value(group, definition.ranking.indicator)
            if score is None or not isfinite(score):
                continue
            if definition.ranking.direction == "ascending":
                score = -score
            signals.append(
                Signal(
                    strategy_id=self.strategy_id,
                    trade_date=context.trade_date,
                    symbol=str(symbol),
                    signal_type="RULE_BUILDER_SCORE",
                    score=score,
                    model_version=f"rule-schema-v{definition.schema_version}",
                )
            )
        return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))


def _evaluate_rule(group: pd.DataFrame, rule: RuleSpec) -> bool:
    left = _indicator_value(group, rule.left)
    right = _indicator_value(group, rule.right) if rule.right is not None else rule.value
    if left is None or right is None or not isfinite(left) or not isfinite(right):
        return False
    if rule.operator == "greater_than":
        return left > right
    if rule.operator == "greater_or_equal":
        return left >= right
    if rule.operator == "less_than":
        return left < right
    if rule.operator == "less_or_equal":
        return left <= right
    return False


def _indicator_value(group: pd.DataFrame, indicator: IndicatorSpec | None) -> float | None:
    if indicator is None:
        return None
    close = group["adjusted_close"].dropna()
    if close.empty:
        return None
    window = indicator.window
    if indicator.name == "close":
        return float(close.iloc[-1])
    assert window is not None
    if indicator.name == "return":
        if len(close) < window + 1 or float(close.iloc[-window - 1]) <= 0:
            return None
        return float(close.iloc[-1] / close.iloc[-window - 1] - 1.0)
    if indicator.name == "moving_average":
        if len(close) < window:
            return None
        return float(close.tail(window).mean())
    if indicator.name == "volatility":
        if len(close) < window + 1:
            return None
        value = close.tail(window + 1).pct_change(fill_method=None).dropna().std() * sqrt(
            _TRADING_DAYS
        )
        return float(value) if pd.notna(value) else None
    if indicator.name == "average_amount":
        amount = group["amount"].dropna()
        if len(amount) < window:
            return None
        return float(amount.tail(window).mean())
    if indicator.name in {"previous_high", "previous_low"}:
        if len(close) < window + 1:
            return None
        previous = close.iloc[-window - 1 : -1]
        return float(previous.max() if indicator.name == "previous_high" else previous.min())
    if indicator.name == "rsi":
        if len(close) < window + 1:
            return None
        changes = close.tail(window + 1).diff().dropna()
        average_gain = float(changes.clip(lower=0).mean())
        average_loss = float((-changes.clip(upper=0)).mean())
        if average_loss == 0:
            return 100.0 if average_gain > 0 else 50.0
        return 100.0 - 100.0 / (1.0 + average_gain / average_loss)
    if indicator.name == "drawdown":
        if len(close) < window:
            return None
        recent = close.tail(window)
        peak = float(recent.max())
        return float(recent.iloc[-1] / peak - 1.0) if peak > 0 else None
    return None
