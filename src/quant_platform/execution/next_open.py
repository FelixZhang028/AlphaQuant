"""T+1 next-open paper execution model."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from quant_platform.accounts.account import Account
from quant_platform.core.exceptions import AccountError
from quant_platform.execution.models import Fill, Order, OrderSide, OrderStatus


@dataclass(frozen=True)
class ExecutionConfig:
    """Paper execution fees, slippage, and lot size."""

    lot_size: int = 100
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stamp_tax_rate: float = 0.0005
    slippage_rate: float = 0.0005
    reject_unknown_status: bool = True


class NextOpenExecutionModel:
    """Execute eligible orders at raw next-open price plus configurable costs."""

    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config

    def execute(
        self,
        orders: list[Order],
        market_rows: pd.DataFrame,
        account: Account,
    ) -> tuple[list[Order], list[Fill]]:
        """Execute sells before buys and apply successful fills to the account."""

        rows = {str(row["symbol"]): row for _, row in market_rows.iterrows()}
        updated: list[Order] = []
        fills: list[Fill] = []
        for order in sorted(
            orders, key=lambda item: (item.side != OrderSide.SELL, item.symbol)
        ):
            row = rows.get(order.symbol)
            reason = self._rejection_reason(order, row)
            if reason:
                updated.append(order.with_status(OrderStatus.REJECTED, reason))
                continue
            assert row is not None
            raw_open = float(row["raw_open"])
            price = raw_open * (
                1.0 + self.config.slippage_rate
                if order.side == OrderSide.BUY
                else 1.0 - self.config.slippage_rate
            )
            quantity = self._executable_quantity(order, price, account)
            if quantity <= 0:
                updated.append(
                    order.with_status(
                        OrderStatus.REJECTED, "insufficient cash or quantity"
                    )
                )
                continue
            notional = quantity * price
            commission = max(
                self.config.minimum_commission, notional * self.config.commission_rate
            )
            stamp_tax = (
                notional * self.config.stamp_tax_rate
                if order.side == OrderSide.SELL
                else 0.0
            )
            fill = Fill.create(order, quantity, price, commission, stamp_tax)
            try:
                account.apply_fill(fill)
            except AccountError as exc:
                updated.append(order.with_status(OrderStatus.FAILED, str(exc)))
                continue
            fills.append(fill)
            updated.append(order.with_status(OrderStatus.FILLED))
        return updated, fills

    def _rejection_reason(self, order: Order, row: pd.Series | None) -> str | None:
        if row is None:
            return "missing execution-day market data"
        if bool(row.get("is_suspended", False)):
            return "security suspended"
        if (
            self.config.reject_unknown_status
            and str(row.get("quality_status", "OK")) != "OK"
        ):
            return f"market status is {row.get('quality_status')}"
        raw_open = float(row["raw_open"])
        up_limit = row.get("up_limit")
        down_limit = row.get("down_limit")
        if (
            order.side == OrderSide.BUY
            and pd.notna(up_limit)
            and raw_open >= float(up_limit) - 1e-9
        ):
            return "opened at upper price limit"
        if (
            order.side == OrderSide.SELL
            and pd.notna(down_limit)
            and raw_open <= float(down_limit) + 1e-9
        ):
            return "opened at lower price limit"
        return None

    def _executable_quantity(self, order: Order, price: float, account: Account) -> int:
        if order.side == OrderSide.SELL:
            position = account.positions.get(order.symbol)
            return min(order.quantity, position.available_quantity if position else 0)
        available_for_notional = max(account.cash - self.config.minimum_commission, 0.0)
        per_share_with_cost = price * (1.0 + self.config.commission_rate)
        affordable = int(
            available_for_notional / per_share_with_cost / self.config.lot_size
        )
        affordable *= self.config.lot_size
        return min(order.quantity, affordable)
