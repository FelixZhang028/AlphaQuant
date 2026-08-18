"""Atomic long-only paper account."""

from __future__ import annotations

from datetime import date

from quant_platform.accounts.models import AccountSnapshot, Position
from quant_platform.core.exceptions import AccountError
from quant_platform.execution.models import Fill, OrderSide


class Account:
    """Maintain cash, T+1 positions, and end-of-day net asset value."""

    def __init__(self, account_id: str, initial_cash: float) -> None:
        if initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        self.account_id = account_id
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: dict[str, Position] = {}
        self.snapshots: list[AccountSnapshot] = []
        self.processed_fill_ids: set[str] = set()
        self.realized_pnl = 0.0
        self._peak_equity = float(initial_cash)

    def start_day(self) -> None:
        """Release existing holdings for sale at the next trading day."""

        for position in self.positions.values():
            position.available_quantity = position.quantity

    def apply_fill(self, fill: Fill) -> None:
        """Apply a fill atomically, rejecting duplicate or invalid state changes."""

        if fill.fill_id in self.processed_fill_ids:
            raise AccountError(f"Fill already processed: {fill.fill_id}")
        cash = self.cash
        positions = self.positions.copy()
        realized_pnl = self.realized_pnl
        existing = positions.get(fill.symbol)
        position = (
            Position(
                symbol=fill.symbol,
                quantity=existing.quantity,
                available_quantity=existing.available_quantity,
                average_cost=existing.average_cost,
            )
            if existing is not None
            else Position(symbol=fill.symbol)
        )
        positions[fill.symbol] = position
        notional = fill.quantity * fill.price
        fees = fill.commission + fill.stamp_tax

        if fill.side == OrderSide.BUY:
            total = notional + fees
            if total > cash + 1e-9:
                raise AccountError(f"Insufficient cash for fill {fill.fill_id}")
            old_cost = position.quantity * position.average_cost
            position.quantity += fill.quantity
            position.average_cost = (old_cost + total) / position.quantity
            cash -= total
        else:
            if fill.quantity > position.available_quantity:
                raise AccountError(f"Insufficient sellable quantity for fill {fill.fill_id}")
            realized_pnl += notional - fees - fill.quantity * position.average_cost
            position.quantity -= fill.quantity
            position.available_quantity -= fill.quantity
            cash += notional - fees
            if position.quantity == 0:
                positions.pop(fill.symbol)

        if cash < -1e-8:
            raise AccountError(f"Fill would make cash negative: {fill.fill_id}")
        self.cash = cash
        self.positions = positions
        self.realized_pnl = realized_pnl
        self.processed_fill_ids.add(fill.fill_id)

    def mark_to_market(self, trade_date: date, closing_prices: dict[str, float]) -> AccountSnapshot:
        """Value positions at raw closing prices and append an end-of-day snapshot."""

        market_value = sum(
            position.quantity * closing_prices.get(symbol, 0.0)
            for symbol, position in self.positions.items()
        )
        equity = self.cash + market_value
        previous_equity = self.snapshots[-1].equity if self.snapshots else self.initial_cash
        daily_return = equity / previous_equity - 1.0 if previous_equity else 0.0
        self._peak_equity = max(self._peak_equity, equity)
        drawdown = equity / self._peak_equity - 1.0 if self._peak_equity else 0.0
        snapshot = AccountSnapshot(
            trade_date=trade_date,
            cash=self.cash,
            market_value=market_value,
            equity=equity,
            daily_return=daily_return,
            drawdown=drawdown,
        )
        self.snapshots.append(snapshot)
        return snapshot
