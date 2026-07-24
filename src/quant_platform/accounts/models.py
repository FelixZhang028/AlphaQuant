"""Account domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Position:
    """Long stock position with T+1 sellable quantity tracking."""

    symbol: str
    quantity: int = 0
    available_quantity: int = 0
    average_cost: float = 0.0


@dataclass(frozen=True)
class AccountSnapshot:
    """End-of-day account valuation."""

    trade_date: date
    cash: float
    market_value: float
    equity: float
    daily_return: float
    drawdown: float
