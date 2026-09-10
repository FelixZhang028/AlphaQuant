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
            # 成本锚定因子按数量加权调和平均更新：保持 Σ(N_i/F_i) 恒等，
            # 使 blended 锚定估值与逐笔买入分别锚定的结果一致（算术平均会失真）。
            old_units = (
                position.quantity / position.cost_adj_factor
                if position.cost_adj_factor > 0
                else 0.0
            )
            new_units = (
                fill.quantity / fill.adj_factor if fill.adj_factor > 0 else float(fill.quantity)
            )
            position.quantity += fill.quantity
            position.average_cost = (old_cost + total) / position.quantity
            anchor_units = old_units + new_units
            position.cost_adj_factor = (
                position.quantity / anchor_units if anchor_units > 0 else 1.0
            )
            cash -= total
        else:
            if fill.quantity > position.available_quantity:
                raise AccountError(f"Insufficient sellable quantity for fill {fill.fill_id}")
            # 卖出按成本锚定价结算：raw × F(t)/cost_adj_factor，与估值同一口径，
            # 跨除权日卖出不再出现净值跳变（等价于把分红送转在卖出时点变现）。
            anchor_ratio = (
                fill.adj_factor / position.cost_adj_factor
                if fill.adj_factor > 0 and position.cost_adj_factor > 0
                else 1.0
            )
            settled_notional = notional * anchor_ratio
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
