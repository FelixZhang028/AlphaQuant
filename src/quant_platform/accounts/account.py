"""Atomic long-only paper account."""

from __future__ import annotations

from datetime import date
from math import isclose, isfinite

from quant_platform.accounts.models import AccountSnapshot, CorporateAction, Position
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
        self._corporate_actions: set[tuple[str, date]] = set()
        self._dividends: list[tuple[date, float]] = []
        self._locked_shares: list[tuple[date, str, int]] = []

    @property
    def dividend_receivable(self) -> float:
        return sum(amount for _, amount in self._dividends)

    def start_day(self, trade_date: date | None = None) -> None:
        """Release existing holdings for sale at the next trading day."""

        if trade_date is not None:
            self.cash += sum(amount for day, amount in self._dividends if day <= trade_date)
            self._dividends = [(day, amount) for day, amount in self._dividends if day > trade_date]
            self._locked_shares = [item for item in self._locked_shares if item[0] > trade_date]
        for position in self.positions.values():
            locked = sum(qty for _, symbol, qty in self._locked_shares if symbol == position.symbol)
            position.available_quantity = position.quantity - locked

    def apply_corporate_action(self, action: CorporateAction) -> None:
        """Book entitlements on ex-date before trades; cash is usable on pay-date."""
        key = (action.symbol, action.ex_date)
        if key in self._corporate_actions:
            raise AccountError(f"Corporate action already processed: {key}")
        position = self.positions.get(action.symbol)
        if position is not None:
            if any(symbol == action.symbol for _, symbol, _ in self._locked_shares):
                raise AccountError(
                    "Overlapping unlisted share entitlements require explicit handling"
                )
            exact_quantity = position.quantity * action.share_multiplier
            quantity = round(exact_quantity)
            if not isclose(exact_quantity, quantity, abs_tol=1e-8, rel_tol=0):
                raise AccountError("Fractional corporate-action shares require explicit settlement")
            dividend = position.quantity * action.cash_per_share
            added = quantity - position.quantity
            position.average_cost /= action.share_multiplier
            position.quantity = quantity
            listing_date = action.share_listing_date or action.ex_date
            if listing_date > action.ex_date:
                self._locked_shares.append((listing_date, action.symbol, added))
            else:
                position.available_quantity += added
            pay_date = action.pay_date or action.ex_date
            if pay_date > action.ex_date:
                self._dividends.append((pay_date, dividend))
            else:
                self.cash += dividend
            self.realized_pnl += dividend
        self._corporate_actions.add(key)

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
                cost_adj_factor=existing.cost_adj_factor,
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
            if position.quantity == 0:
                position.cost_adj_factor = (
                    fill.adj_factor if isfinite(fill.adj_factor) and fill.adj_factor > 0 else 1.0
                )
            position.quantity += fill.quantity
            position.average_cost = (old_cost + total) / position.quantity
            cash -= total
        else:
            if fill.quantity > position.available_quantity:
                raise AccountError(f"Insufficient sellable quantity for fill {fill.fill_id}")
            settled_notional = notional
            realized_pnl += settled_notional - fees - fill.quantity * position.average_cost
            position.quantity -= fill.quantity
            position.available_quantity -= fill.quantity
            cash += settled_notional - fees
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
        equity = self.cash + market_value + self.dividend_receivable
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
            dividend_receivable=self.dividend_receivable,
        )
        self.snapshots.append(snapshot)
        return snapshot
