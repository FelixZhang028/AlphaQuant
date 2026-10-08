"""组合账户：现金、持仓、成本。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Position(BaseModel):
    symbol: str
    quantity: float = 0.0
    avg_cost: float = 0.0


class Portfolio(BaseModel):
    """模拟组合账户。"""

    cash: float = 100_000.0
    positions: dict[str, Position] = Field(default_factory=dict)

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash + sum(
            p.quantity * prices.get(sym, p.avg_cost) for sym, p in self.positions.items()
        )

    def apply_buy(self, symbol: str, quantity: float, price: float, commission: float) -> None:
        cost = quantity * price + commission
        if cost > self.cash + 1e-9:
            raise RuntimeError(
                f"insufficient cash: need {cost:.2f}, have {self.cash:.2f}"
            )
        self.cash -= cost
        pos = self.positions.get(symbol, Position(symbol=symbol))
        total_qty = pos.quantity + quantity
        pos.avg_cost = (
            (pos.avg_cost * pos.quantity + price * quantity) / total_qty if total_qty else 0.0
        )
        pos.quantity = total_qty
        self.positions[symbol] = pos

    def apply_sell(self, symbol: str, quantity: float, price: float, commission: float) -> None:
        pos = self.positions.get(symbol)
        if pos is None or pos.quantity < quantity - 1e-9:
            raise RuntimeError(f"insufficient position to sell {quantity} of {symbol}")
        pos.quantity -= quantity
        self.cash += quantity * price - commission
