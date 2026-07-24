"""Equal-weight target portfolio constructor."""

from __future__ import annotations

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

        selected = sorted(signals, key=lambda signal: (-signal.score, signal.symbol))[
            : self.top_n
        ]
        if not selected:
            return []
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
