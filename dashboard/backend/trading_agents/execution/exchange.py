"""模拟交易所撮合（机制 M5）。

规则（回测与实盘模拟共用，保证口径一致）：
- 撮合基准价：快照收盘价 ``last_close``（或提案指定的更低/更高入场价的
  最小可实现值——本实现统一按基准价撮合）。
- 滑点：买入价 = 基准价 × (1 + slippage_bps/10000)，卖出反向。
- 手续费：成交额 × commission_bps/10000，不低于 min_commission。
- 交收：T+settlement_days（默认 T+1）。
- 被驳回/conditional 仓位为 0 的决策不成交（返回 None）。
"""

from __future__ import annotations

import datetime as dt

from trading_agents.config import ExecutionSettings
from trading_agents.execution.portfolio import Portfolio
from trading_agents.schemas import Decision, ExecutionFill, MarketSnapshot
from trading_agents.schemas.models import ApprovalStatus, TradeAction


class SimulatedExchange:
    def __init__(self, settings: ExecutionSettings) -> None:
        self.settings = settings

    def _settlement(self, trade_date: dt.date) -> dt.date:
        d = trade_date
        added = 0
        while added < self.settings.settlement_days:
            d += dt.timedelta(days=1)
            if d.weekday() < 5:
                added += 1
        return d

    def execute(
        self,
        decision: Decision,
        snapshot: MarketSnapshot,
        portfolio: Portfolio,
    ) -> ExecutionFill | None:
        """撮合已批准决策；被驳回或动作为 hold 时返回 None。"""
        if decision.status == ApprovalStatus.REJECTED:
            return None
        action = decision.final_action
        if action == TradeAction.HOLD or decision.final_position_pct <= 0:
            return None
        ref = snapshot.last_close
        slip = ref * self.settings.slippage_bps / 10_000
        if action == TradeAction.BUY:
            price = ref + slip
            equity = portfolio.equity({decision.ticker: ref})
            budget = equity * decision.final_position_pct
            quantity = budget / price
            commission = max(
                quantity * price * self.settings.commission_bps / 10_000,
                self.settings.min_commission,
            )
            portfolio.apply_buy(decision.ticker, quantity, price, commission)
        else:
            price = ref - slip
            pos = portfolio.positions.get(decision.ticker)
            quantity = pos.quantity if pos else 0.0
            if quantity <= 0:
                return None
            commission = max(
                quantity * price * self.settings.commission_bps / 10_000,
                self.settings.min_commission,
            )
            portfolio.apply_sell(decision.ticker, quantity, price, commission)
        return ExecutionFill(
            ticker=decision.ticker,
            trade_date=snapshot.as_of_date,
            action=action,
            quantity=round(quantity, 6),
            price=round(price, 6),
            reference_price=ref,
            slippage=round(slip, 6),
            commission=round(commission, 6),
            settlement_date=self._settlement(snapshot.as_of_date),
            timestamp=dt.datetime.now(dt.UTC),
        )
