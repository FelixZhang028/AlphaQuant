"""T+1 next-open paper execution model."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt

import pandas as pd

from quant_platform.accounts.account import Account
from quant_platform.core.exceptions import AccountError
from quant_platform.execution.costs import stamp_rate, transfer_rate
from quant_platform.execution.models import (
    Fill,
    Order,
    OrderRejectReason,
    OrderSide,
    OrderStatus,
)


@dataclass(frozen=True)
class ExecutionConfig:
    """Paper execution fees, slippage, and lot size."""

    lot_size: int = 100
    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stamp_tax_rate: float = 0.0005
    slippage_rate: float = 0.0005
    reject_unknown_status: bool = True
    historical_fees: bool = True
    transfer_fee_rate: float = 0.00001
    max_participation: float = 0.01
    impact_coefficient: float = 0.001
    max_orders_per_day: int = 1000

    def __post_init__(self) -> None:
        if not 0 < self.max_participation <= 1:
            raise ValueError("max_participation must be in (0, 1]")
        if self.lot_size <= 0 or self.max_orders_per_day <= 0:
            raise ValueError("lot size and order limit must be positive")
        for value in (
            self.commission_rate,
            self.minimum_commission,
            self.stamp_tax_rate,
            self.transfer_fee_rate,
            self.slippage_rate,
            self.impact_coefficient,
        ):
            if not isfinite(value) or value < 0:
                raise ValueError("cost parameters must be finite and nonnegative")


class NextOpenExecutionModel:
    """Execute eligible orders at raw next-open price plus configurable costs."""

    def __init__(self, config: ExecutionConfig) -> None:
        self.config = config
        self.reset()

    def reset(self) -> None:
        self._used = {}
        self._order_counts = {}

    def execute(
        self,
        orders: list[Order],
        market_rows: pd.DataFrame,
        account: Account,
        adj_factors: dict[str, float] | None = None,
    ) -> tuple[list[Order], list[Fill]]:
        """Execute sells before buys and apply successful fills to the account.

        ``adj_factors`` 是引擎前向填充的最近复权因子：当日行缺因子时兜底，
        仍取不到则回退 1（未复权口径），由引擎计入有效性告警。
        """

        rows = {str(row["symbol"]): pd.Series(row) for row in market_rows.to_dict("records")}
        # Per execution batch: engine supplies all orders for a day together.
        used = self._used
        updated: list[Order] = []
        fills: list[Fill] = []
        for order in sorted(orders, key=lambda item: (item.side != OrderSide.SELL, item.symbol)):
            day = order.execution_date
            key = (day, order.symbol)
            self._order_counts[day] = self._order_counts.get(day, 0) + 1
            if self._order_counts[day] > self.config.max_orders_per_day:
                updated.append(order.with_status(OrderStatus.REJECTED, "DAILY_ORDER_LIMIT"))
                continue
            row = rows.get(order.symbol)
            reason = self._rejection_reason(order, row)
            if reason:
                updated.append(order.with_status(OrderStatus.REJECTED, reason))
                continue
            assert row is not None
            volume = pd.to_numeric(row.get("volume"), errors="coerce")
            reference_volume = pd.to_numeric(row.get("liquidity_volume", volume), errors="coerce")
            if not isfinite(float(volume)) or not isfinite(float(reference_volume)):
                updated.append(order.with_status(OrderStatus.REJECTED, "MISSING_LIQUIDITY"))
                continue
            capacity = max(
                0,
                int(min(volume, reference_volume) * self.config.max_participation)
                - used.get(key, 0),
            )
            quantity = min(order.remaining_quantity, capacity)
            if order.side == OrderSide.BUY:
                quantity = quantity // self.config.lot_size * self.config.lot_size
            if quantity <= 0:
                updated.append(order.with_status(OrderStatus.REJECTED, "LIQUIDITY_LIMIT"))
                continue
            fee_rate = (
                transfer_rate(order.execution_date, order.symbol)
                if self.config.historical_fees
                else self.config.transfer_fee_rate
            )
            impact = self.config.impact_coefficient * sqrt(
                (used.get(key, 0) + quantity) / max(reference_volume, 1)
            )
            slippage = self.config.slippage_rate + impact
            raw_open = float(row["raw_open"])
            price = raw_open * (1.0 + slippage if order.side == OrderSide.BUY else 1.0 - slippage)
            if (
                price <= 0
                or price > float(row.get("up_limit", float("inf")))
                or price < float(row.get("down_limit", 0))
            ):
                updated.append(order.with_status(OrderStatus.REJECTED, "IMPACT_OUTSIDE_LIMIT"))
                continue
            quantity = min(quantity, self._executable_quantity(order, price, account, fee_rate))
            if quantity <= 0:
                updated.append(
                    order.with_status(
                        OrderStatus.REJECTED,
                        OrderRejectReason.INSUFFICIENT_CASH_OR_QUANTITY.value,
                    )
                )
                continue
            notional = quantity * price
            commission = max(self.config.minimum_commission, notional * self.config.commission_rate)
            stamp_tax = (
                notional
                * (
                    stamp_rate(order.execution_date)
                    if self.config.historical_fees
                    else self.config.stamp_tax_rate
                )
                if order.side == OrderSide.SELL
                else 0.0
            )
            fill = Fill.create(
                order,
                quantity,
                price,
                commission,
                stamp_tax,
                reference_price=raw_open,
                slippage_cost=abs(price - raw_open) * quantity,
                adj_factor=self._resolve_adj_factor(order.symbol, row, adj_factors),
                transfer_fee=notional * fee_rate,
            )
            try:
                account.apply_fill(fill)
            except AccountError as exc:
                updated.append(order.with_status(OrderStatus.FAILED, str(exc)))
                continue
            fills.append(fill)
            used[key] = used.get(key, 0) + quantity
            updated.append(order.with_fill(quantity))
        return updated, fills

    @staticmethod
    def _resolve_adj_factor(
        symbol: str, row: pd.Series, adj_factors: dict[str, float] | None
    ) -> float:
        """Resolve the trade-date adjustment factor, defaulting to a raw ratio of 1."""

        value = row.get("adj_factor", pd.NA)
        if pd.notna(value):
            try:
                factor = float(value)
            except (TypeError, ValueError):
                factor = 0.0
            if isfinite(factor) and factor > 0:
                return factor
        fallback = (adj_factors or {}).get(str(symbol))
        if fallback and isfinite(fallback) and fallback > 0:
            return float(fallback)
        return 1.0

    def _rejection_reason(self, order: Order, row: pd.Series | None) -> str | None:
        if row is None:
            return OrderRejectReason.MISSING_EXECUTION_BAR.value
        suspended = row.get("is_suspended", pd.NA)
        if pd.isna(suspended):
            if self.config.reject_unknown_status:
                return OrderRejectReason.UNKNOWN_SUSPENSION_STATUS.value
        elif bool(suspended):
            return OrderRejectReason.SUSPENDED.value
        quality_status = row.get("quality_status", pd.NA)
        if self.config.reject_unknown_status:
            if pd.isna(quality_status) or str(quality_status) == "UNKNOWN_STATUS":
                return OrderRejectReason.UNKNOWN_MARKET_STATUS.value
            if str(quality_status) != "OK":
                return OrderRejectReason.MARKET_DATA_NOT_TRADABLE.value
        raw_open_value = row.get("raw_open")
        if raw_open_value is None or pd.isna(raw_open_value):
            return OrderRejectReason.INVALID_EXECUTION_PRICE.value
        raw_open = float(raw_open_value)
        if raw_open <= 0:
            return OrderRejectReason.INVALID_EXECUTION_PRICE.value
        up_limit = row.get("up_limit")
        down_limit = row.get("down_limit")
        if self.config.reject_unknown_status and (pd.isna(up_limit) or pd.isna(down_limit)):
            return OrderRejectReason.UNKNOWN_PRICE_LIMIT.value
        if (
            order.side == OrderSide.BUY
            and pd.notna(up_limit)
            and raw_open >= float(up_limit) - 1e-9
        ):
            return OrderRejectReason.OPEN_AT_UPPER_LIMIT.value
        if (
            order.side == OrderSide.SELL
            and pd.notna(down_limit)
            and raw_open <= float(down_limit) + 1e-9
        ):
            return OrderRejectReason.OPEN_AT_LOWER_LIMIT.value
        return None

    def _executable_quantity(
        self, order: Order, price: float, account: Account, transfer: float = 0.0
    ) -> int:
        if order.side == OrderSide.SELL:
            position = account.positions.get(order.symbol)
            return min(order.remaining_quantity, position.available_quantity if position else 0)
        available_for_notional = max(account.cash - self.config.minimum_commission, 0.0)
        per_share_with_cost = price * (1.0 + self.config.commission_rate + transfer)
        affordable = int(available_for_notional / per_share_with_cost / self.config.lot_size)
        affordable *= self.config.lot_size
        return min(order.remaining_quantity, affordable)
