"""Initial A-share momentum strategy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyParameter


@dataclass(frozen=True)
class MomentumParameters:
    """Configurable momentum windows and liquidity threshold."""

    short_window: int = 20
    long_window: int = 60
    minimum_average_amount: float = 20_000_000.0


class AShareMomentumStrategy(Strategy):
    """Rank positive long-term trends by shorter-term momentum."""

    plugin_name = "a_share_momentum"
    display_name = "A股动量策略"
    description = "过滤长期趋势为负和流动性不足的股票，按短期动量排序。"
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "short_window",
            "短期窗口",
            ParameterKind.INTEGER,
            20,
            "用于动量排名的交易日数量",
            minimum=2,
            maximum=250,
        ),
        StrategyParameter(
            "long_window",
            "长期窗口",
            ParameterKind.INTEGER,
            60,
            "用于趋势过滤的交易日数量",
            minimum=3,
            maximum=500,
        ),
        StrategyParameter(
            "minimum_average_amount",
            "最低20日平均成交额",
            ParameterKind.NUMBER,
            20_000_000.0,
            "单位：元",
            minimum=0,
        ),
    )
    required_fields = frozenset({"symbol", "trade_date", "adjusted_close", "amount"})

    def __init__(self, strategy_id: str, parameters: MomentumParameters) -> None:
        if parameters.short_window <= 0 or parameters.long_window <= parameters.short_window:
            raise ValueError("Momentum windows must satisfy 0 < short < long")
        self.strategy_id = strategy_id
        self.config = parameters

    @classmethod
    def from_parameters(
        cls, strategy_id: str, parameters: dict[str, Any]
    ) -> AShareMomentumStrategy:
        """Build the strategy from catalog-validated values."""

        return cls(
            strategy_id,
            MomentumParameters(
                short_window=int(parameters["short_window"]),
                long_window=int(parameters["long_window"]),
                minimum_average_amount=float(parameters["minimum_average_amount"]),
            ),
        )

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """Calculate point-in-time momentum signals."""

        context.require_fields(self.required_fields)
        history = context.history(
            fields=["adjusted_close", "amount"],
            lookback=self.config.long_window + 1,
        )
        cutoff = pd.Timestamp(context.trade_date)
        signals: list[Signal] = []
        for symbol, group in history.groupby("symbol", observed=True):
            group = group.dropna(subset=["adjusted_close"])
            if len(group) <= self.config.long_window:
                continue
            latest = group.iloc[-1]
            if pd.Timestamp(latest["trade_date"]) != cutoff:
                continue
            current = float(latest["adjusted_close"])
            short_base = float(group.iloc[-self.config.short_window - 1]["adjusted_close"])
            long_base = float(group.iloc[-self.config.long_window - 1]["adjusted_close"])
            if short_base <= 0 or long_base <= 0:
                continue
            short_momentum = current / short_base - 1.0
            long_momentum = current / long_base - 1.0
            average_amount = pd.to_numeric(group.tail(20)["amount"], errors="coerce").mean()
            if long_momentum <= 0 or average_amount < self.config.minimum_average_amount:
                continue
            signals.append(
                Signal(
                    strategy_id=self.strategy_id,
                    trade_date=context.trade_date,
                    symbol=str(symbol),
                    signal_type="MOMENTUM_SCORE",
                    score=short_momentum,
                )
            )
        return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))
