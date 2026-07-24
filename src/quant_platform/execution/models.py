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
    """Paper-order lifecycle state."""

    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


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

    def with_status(self, status: OrderStatus, reason: str | None = None) -> Order:
        """Return an updated immutable order."""

        return replace(self, status=status, reject_reason=reason)


@dataclass(frozen=True)
class Fill:
    """Executed paper-trade result consumed by an account."""

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

    @classmethod
    def create(
        cls,
        order: Order,
        quantity: int,
        price: float,
        commission: float,
        stamp_tax: float,
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
        )
