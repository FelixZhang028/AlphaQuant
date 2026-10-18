"""Equal-weight target portfolio constructor."""

from __future__ import annotations

from math import fsum
from typing import cast

from quant_platform.portfolio.models import TargetPosition
from quant_platform.signals.models import Signal


class EqualWeightPortfolio:
    """Select the highest scored signals and allocate equal weights."""

    def __init__(self, top_n: int) -> None:
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        self.top_n = top_n

    def construct(self, signals: list[Signal]) -> list[TargetPosition]:
        """Build equal-weight targets; an empty signal set means all cash."""

        if not signals:
            return []
        explicit = [signal for signal in signals if signal.target_weight is not None]
        if explicit and len(explicit) != len(signals):
            raise ValueError("signals must either all specify target_weight or all omit it")
        if explicit:
            total_weight = fsum(cast(float, signal.target_weight) for signal in explicit)
            if any(cast(float, signal.target_weight) <= 0.0 for signal in explicit):
                raise ValueError("explicit signal target weights must be positive")
            if total_weight > 1.0 + 1e-9:
                raise ValueError("explicit signal target weights must not exceed one")
            return [
                TargetPosition(
                    strategy_id=signal.strategy_id,
                    signal_date=signal.trade_date,
                    symbol=signal.symbol,
                    target_weight=cast(float, signal.target_weight),
                )
                for signal in sorted(
                    explicit,
                    key=lambda signal: (-signal.score, signal.symbol),
                )
            ]

        selected = sorted(signals, key=lambda signal: (-signal.score, signal.symbol))[: self.top_n]
        weight = 1.0 / len(selected)
        return [
            TargetPosition(
                strategy_id=signal.strategy_id,
                signal_date=signal.trade_date,
                symbol=signal.symbol,
                target_weight=weight,
            )
            for signal in selected
        ]
