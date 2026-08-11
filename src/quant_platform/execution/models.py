"""Order and fill domain models."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import uuid4


class OrderSide(StrEnum):
    """Long-only order side."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    """Order lifecycle shared by backtest, paper, and future live adapters."""

    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class OrderRejectReason(StrEnum):
    """Stable machine-readable reasons for rejecting simulated orders."""

    MISSING_EXECUTION_BAR = "MISSING_EXECUTION_BAR"
    SUSPENDED = "SUSPENDED"
    UNKNOWN_SUSPENSION_STATUS = "UNKNOWN_SUSPENSION_STATUS"
    UNKNOWN_MARKET_STATUS = "UNKNOWN_MARKET_STATUS"
    MARKET_DATA_NOT_TRADABLE = "MARKET_DATA_NOT_TRADABLE"
    UNKNOWN_PRICE_LIMIT = "UNKNOWN_PRICE_LIMIT"
    OPEN_AT_UPPER_LIMIT = "OPEN_AT_UPPER_LIMIT"
    OPEN_AT_LOWER_LIMIT = "OPEN_AT_LOWER_LIMIT"
    INSUFFICIENT_CASH_OR_QUANTITY = "INSUFFICIENT_CASH_OR_QUANTITY"


@dataclass(frozen=True)
class Order:
    """Quantity order created after a signal for a later execution date."""

    order_id: str
    strategy_id: str
    symbol: str
    side: OrderSide
    quantity: int
    signal_date: date
    execution_date: date
    status: OrderStatus = OrderStatus.CREATED
    filled_quantity: int = 0
    reject_reason: str | None = None

    @classmethod
    def create(
        cls,
        strategy_id: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        signal_date: date,
        execution_date: date,
    ) -> Order:
        """Create an order with a unique identifier."""

        return cls(
            str(uuid4()),
            strategy_id,
            symbol,
            side,
            quantity,
            signal_date,
            execution_date,
        )

    @property
    def remaining_quantity(self) -> int:
        """Return the unfilled quantity."""

        return max(self.quantity - self.filled_quantity, 0)

    def with_status(self, status: OrderStatus, reason: str | None = None) -> Order:
        """Return an updated immutable order."""

        return replace(self, status=status, reject_reason=reason)

    def with_fill(self, quantity: int) -> Order:
        """Apply a fill quantity and derive full or partial status."""

        if quantity <= 0 or self.filled_quantity + quantity > self.quantity:
            raise ValueError("invalid order fill quantity")
        filled = self.filled_quantity + quantity
        status = OrderStatus.FILLED if filled == self.quantity else OrderStatus.PARTIALLY_FILLED
        return replace(self, filled_quantity=filled, status=status)


@dataclass(frozen=True)
class Fill:
    """Executed paper trade, including its reference price and slippage cost."""

    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    commission: float
    stamp_tax: float
    trade_date: date
    filled_at: datetime
    reference_price: float
    slippage_cost: float

    @classmethod
    def create(
        cls,
        order: Order,
        quantity: int,
        price: float,
        commission: float,
        stamp_tax: float,
        reference_price: float | None = None,
        slippage_cost: float = 0.0,
    ) -> Fill:
        """Create a fill for an order on its configured execution date."""

        return cls(
            fill_id=str(uuid4()),
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=quantity,
            price=price,
            commission=commission,
            stamp_tax=stamp_tax,
            trade_date=order.execution_date,
            filled_at=datetime.now(UTC),
            reference_price=(price if reference_price is None else reference_price),
            slippage_cost=slippage_cost,
        )
