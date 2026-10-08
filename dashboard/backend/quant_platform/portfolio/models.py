"""Target portfolio domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class TargetPosition:
    """Desired portfolio weight for a symbol after rebalance."""

    strategy_id: str
    signal_date: date
    symbol: str
    target_weight: float
