from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.rule_based import RuleBasedStrategy
from quant_platform.strategies.rule_schema import (
    IndicatorSpec,
    RankingSpec,
    RuleSpec,
    RuleStrategyDefinition,
)


def _definition() -> RuleStrategyDefinition:
    return RuleStrategyDefinition(
        strategy_id="visual_test",
        name="测试积木策略",
        description="测试",
        entry_logic="all",
        entry_rules=(
            RuleSpec(IndicatorSpec("return", 2), "greater_than", value=0.0),
            RuleSpec(
                IndicatorSpec("close"),
                "greater_than",
                right=IndicatorSpec("moving_average", 3),
            ),
        ),
        ranking=RankingSpec(IndicatorSpec("return", 2), "descending"),
    )


def test_rule_strategy_uses_only_point_in_time_history_and_ranks_signals() -> None:
    dates = pd.date_range("2024-01-01", periods=5, freq="D")
    frame = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "adjusted_close": close,
                "amount": 100_000_000,
            }
            for symbol, closes in {
                "000001.SZ": [10, 10, 11, 12, 1],
                "600000.SH": [10, 10, 10.5, 11, 100],
            }.items()
            for trade_date, close in zip(dates, closes, strict=True)
        ]
    )
    cutoff = date(2024, 1, 4)
    context = StrategyContext.create(cutoff, frame, ["000001.SZ", "600000.SH"])
    strategy = RuleBasedStrategy.from_parameters(
        "visual_test", {"definition_json": _definition().to_json()}
    )

    signals = strategy.generate_signals(context)

    assert [signal.symbol for signal in signals] == ["000001.SZ", "600000.SH"]
    assert signals[0].score > signals[1].score
    assert all(signal.trade_date == cutoff for signal in signals)


def test_ascending_ranking_prefers_lower_values() -> None:
    definition = RuleStrategyDefinition(
        strategy_id="low_volatility_test",
        name="低波测试",
        description="测试",
        entry_logic="all",
        entry_rules=(RuleSpec(IndicatorSpec("return", 2), "greater_than", value=-1.0),),
        ranking=RankingSpec(IndicatorSpec("volatility", 3), "ascending"),
    )
    dates = pd.date_range("2024-01-01", periods=4, freq="D")
    frame = pd.DataFrame(
        [
            {
                "symbol": symbol,
                "trade_date": trade_date,
                "adjusted_close": close,
                "amount": 100_000_000,
            }
            for symbol, closes in {
                "000001.SZ": [10, 10.1, 10.2, 10.3],
                "600000.SH": [10, 12, 9, 11],
            }.items()
            for trade_date, close in zip(dates, closes, strict=True)
        ]
    )
    strategy = RuleBasedStrategy.from_parameters(
        "low_volatility_test", {"definition_json": definition.to_json()}
    )
    context = StrategyContext.create(date(2024, 1, 4), frame, ["000001.SZ", "600000.SH"])

    signals = strategy.generate_signals(context)

    assert signals[0].symbol == "000001.SZ"
