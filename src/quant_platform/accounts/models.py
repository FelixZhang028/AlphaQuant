"""Account domain models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Position:
    """Long stock position with T+1 sellable quantity tracking."""

    symbol: str
    quantity: int = 0
    available_quantity: int = 0
    average_cost: float = 0.0
    # 成本锚定复权因子：买入当日记录 adj_factor，加仓按数量加权调和平均更新，
    # 清仓后随持仓一起移除（下次买入重新锚定）。估值价 = raw_close × F(t)/cost_adj_factor。
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
