"""Translate target weights into lot-rounded quantity orders."""

from __future__ import annotations

from datetime import date

from quant_platform.accounts.account import Account
from quant_platform.execution.models import Order, OrderSide
from quant_platform.portfolio.models import TargetPosition


class OrderGenerator:
    """Generate long-only rebalance orders using signal-day closes as estimates."""

    def __init__(self, lot_size: int = 100) -> None:
        if lot_size <= 0:
            raise ValueError("lot_size must be positive")
        self.lot_size = lot_size

    def generate(
        self,
        targets: list[TargetPosition],
        account: Account,
        signal_date: date,
        execution_date: date,
        closing_prices: dict[str, float],
    ) -> list[Order]:
        """Create sell and buy orders without using execution-day prices."""

        if execution_date <= signal_date:
            raise ValueError("execution_date must be after signal_date")
        equity = self._estimated_equity(account, closing_prices)
        target_map = {target.symbol: target.target_weight for target in targets}
        strategy_id = targets[0].strategy_id if targets else account.account_id
        symbols = set(account.positions) | set(target_map)
        orders: list[Order] = []
        for symbol in sorted(symbols):
            price = closing_prices.get(symbol)
            if price is None or price <= 0:
                continue
            position = account.positions.get(symbol)
            current_quantity = position.quantity if position is not None else 0
            desired_value = equity * target_map.get(symbol, 0.0)
            desired_quantity = int(desired_value / price / self.lot_size) * self.lot_size
            difference = desired_quantity - current_quantity
            if difference == 0:
                continue
            side = OrderSide.BUY if difference > 0 else OrderSide.SELL
            quantity = abs(difference)
            if side == OrderSide.SELL:
                quantity = min(quantity, current_quantity)
            if quantity > 0:
                orders.append(
                    Order.create(
                        strategy_id=strategy_id,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        signal_date=signal_date,
                        execution_date=execution_date,
                    )
                )
        return sorted(orders, key=lambda order: (order.side != OrderSide.SELL, order.symbol))

    @staticmethod
    def _estimated_equity(account: Account, closing_prices: dict[str, float]) -> float:
        return account.cash + sum(
            position.quantity * closing_prices.get(symbol, 0.0)
            for symbol, position in account.positions.items()
        )
