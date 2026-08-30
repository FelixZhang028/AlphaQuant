"""因子合成策略插件（factor_composite）的单元测试。"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd
import pytest

from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.factor_composite import (
    FactorCompositeParameters,
    FactorCompositeStrategy,
)


def _bars(symbols: list[str], days: int = 30) -> pd.DataFrame:
    rows = []
    start = date(2024, 1, 1)
    for symbol_index, symbol in enumerate(symbols):
        price = 10.0 + symbol_index
        for i in range(days):
            day = start + timedelta(days=i)
            price *= 1.001 * (1 + symbol_index * 0.1)
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": day,
                    "adjusted_close": price,
                    "amount": 30_000_000.0,
                }
            )
    return pd.DataFrame(rows)


def test_parameters_roundtrip_and_validation() -> None:
    payload = json.dumps(
        [{"name": "momentum_20", "weight": 2.0}, {"name": "bias_10", "weight": 1.0}],
        ensure_ascii=False,
    )
    params = FactorCompositeParameters.from_json(payload)
    assert [item.name for item in params.components] == ["momentum_20", "bias_10"]
    assert json.loads(params.to_json())[0]["weight"] == 2.0

    with pytest.raises(ConfigurationError, match="非空列表"):
        FactorCompositeParameters.from_json("[]")
    with pytest.raises(ConfigurationError, match="未注册的因子"):
        FactorCompositeParameters.from_json('[{"name": "ghost_factor"}]')
    with pytest.raises(ConfigurationError, match="重复"):
        FactorCompositeParameters.from_json(
            '[{"name": "momentum_20"}, {"name": "momentum_20"}]'
        )


def test_strategy_generates_scores_for_all_symbols() -> None:
    symbols = ["000001.SZ", "000002.SZ", "600000.SH"]
    history = _bars(symbols, days=30)
    trade_date = date(2024, 1, 30)
    context = StrategyContext.create(trade_date, history, symbols)
    strategy = FactorCompositeStrategy.from_parameters(
        "combo_test",
        {
            "factors_json": json.dumps(
                [{"name": "momentum_20", "weight": 1.0}], ensure_ascii=False
            )
        },
    )
    signals = strategy.generate_signals(context)
    assert {signal.symbol for signal in signals} == set(symbols)
    assert all(signal.signal_type == "FACTOR_COMPOSITE_SCORE" for signal in signals)
    # 按分数从高到低排序
    scores = [signal.score for signal in signals]
    assert scores == sorted(scores, reverse=True)


def test_strategy_returns_empty_when_history_too_short() -> None:
    symbols = ["000001.SZ"]
    history = _bars(symbols, days=5)
    context = StrategyContext.create(date(2024, 1, 5), history, symbols)
    strategy = FactorCompositeStrategy.from_parameters(
        "combo_test",
        {"factors_json": '[{"name": "momentum_20", "weight": 1.0}]'},
    )
    assert strategy.generate_signals(context) == []
