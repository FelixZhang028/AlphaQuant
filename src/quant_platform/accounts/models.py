"""Account domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite


@dataclass(frozen=True)
class CorporateAction:
    """Explicit entitlement per pre-event share; never inferred from adjustment factors.

    cash_per_share is the cash entitlement after any modeled tax. Payment and
    share listing dates default to ex_date for same-day synthetic events.
    """

    symbol: str
    ex_date: date
    cash_per_share: float = 0.0
    share_multiplier: float = 1.0
    pay_date: date | None = None
    share_listing_date: date | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.cash_per_share) or self.cash_per_share < 0:
            raise ValueError("cash_per_share must be finite and nonnegative")
        if not isfinite(self.share_multiplier) or self.share_multiplier < 1:
            raise ValueError("share_multiplier must be finite and >= 1")
        if any(
            day is not None and day < self.ex_date
            for day in (self.pay_date, self.share_listing_date)
        ):
            raise ValueError("payment/listing cannot precede ex_date")


@dataclass
class Position:
    """Long stock position with T+1 sellable quantity tracking."""

    symbol: str
    quantity: int = 0
    available_quantity: int = 0
    average_cost: float = 0.0
    # Retained as historical metadata only; never changes cash or valuation.
    cost_adj_factor: float = 1.0


@dataclass(frozen=True)
class AccountSnapshot:
    """End-of-day account valuation."""

    trade_date: date
    cash: float
    market_value: float
    equity: float
    daily_return: float
    drawdown: float
    dividend_receivable: float = 0.0
