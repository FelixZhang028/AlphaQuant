"""Decision -> Signal 映射：把 LLM 多智能体决策翻译成平台信号。"""

from __future__ import annotations

import datetime as dt

from quant_platform.signals.models import Signal
from trading_agents.schemas import Decision
from trading_agents.schemas.models import ApprovalStatus, TradeAction


def decision_to_signal(
    decision: Decision,
    strategy_id: str,
    trade_date: dt.date,
    symbol: str,
    max_weight_per_stock: float,
) -> Signal | None:
    """approved/conditional 且买入且仓位 > 0 时生成做多信号，否则返回 None。

    信号分数取交易员提案的 confidence（无提案时 0.5），目标权重为
    ``final_position_pct`` 与单票上限 ``max_weight_per_stock`` 的较小值。
    """
    if decision.status not in (ApprovalStatus.APPROVED, ApprovalStatus.CONDITIONAL):
        return None
    if decision.final_action != TradeAction.BUY or decision.final_position_pct <= 0:
        return None
    score = decision.proposal.confidence if decision.proposal is not None else 0.5
    return Signal(
        strategy_id=strategy_id,
        trade_date=trade_date,
        symbol=symbol,
        signal_type="LLM_DECISION",
        score=float(score),
        target_weight=min(decision.final_position_pct, max_weight_per_stock),
    )
