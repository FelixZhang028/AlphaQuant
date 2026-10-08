"""组合经理：独立审批路径（机制 M4）。

审批是独立代码路径，不合并进 Trader：
- 风控 veto → 强制驳回（代码级规则，不依赖 LLM）。
- 否则由 LLM 裁决 approved / rejected / conditional；
  conditional 时可缩减仓位。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from trading_agents.agents.base import BaseAgent
from trading_agents.schemas import (
    Decision,
    MarketSnapshot,
    RiskAssessment,
    TradeProposal,
)
from trading_agents.schemas.models import ApprovalStatus, TradeAction


class PMVerdict(BaseModel):
    """PM 裁决的 LLM 侧契约。"""

    status: ApprovalStatus
    final_position_pct: float = 0.0
    conditions: list[str] = Field(default_factory=list)
    rationale: str = ""
    rejection_reason: str = ""


class PortfolioManager(BaseAgent):
    tag = "pm"
    prompt_file = "portfolio_manager"

    def decide(
        self,
        snapshot: MarketSnapshot,
        proposal: TradeProposal,
        risk: RiskAssessment,
    ) -> Decision:
        base = dict(ticker=proposal.ticker, trade_date=snapshot.as_of_date)
        chain = [
            f"proposal.action={proposal.action.value} position_pct={proposal.position_pct}",
            f"risk.veto={risk.veto} drawdown_est={risk.max_drawdown_est}",
        ]
        # 代码级硬规则：风控 veto 必须驳回
        if risk.veto:
            return Decision(
                **base,  # type: ignore[arg-type]
                status=ApprovalStatus.REJECTED,
                final_action=TradeAction.HOLD,
                final_position_pct=0.0,
                rationale_chain=[*chain, "风控否决，强制驳回"],
                proposal=proposal,
                risk=risk,
                rejection_reason=risk.veto_reason or "risk veto",
            )
        content = (
            f"ticker={snapshot.ticker.symbol}\n"
            f"trade_date={snapshot.as_of_date.isoformat()}\n"
            f"last_close={snapshot.last_close}\n"
            f"交易提案: {proposal.model_dump_json()}\n"
            f"风控评估: {risk.model_dump_json()}"
        )
        verdict: PMVerdict = self.ask(content, PMVerdict)  # type: ignore[assignment]
        if verdict.status == ApprovalStatus.APPROVED:
            final_action, final_pct = proposal.action, proposal.position_pct
        elif verdict.status == ApprovalStatus.CONDITIONAL:
            final_action = proposal.action
            final_pct = min(proposal.position_pct, verdict.final_position_pct)
        else:
            final_action, final_pct = TradeAction.HOLD, 0.0
        return Decision(
            **base,  # type: ignore[arg-type]
            status=verdict.status,
            final_action=final_action,
            final_position_pct=final_pct,
            conditions=[*risk.conditions, *verdict.conditions],
            rationale_chain=[*chain, f"pm: {verdict.rationale}"],
            proposal=proposal,
            risk=risk,
            rejection_reason=verdict.rejection_reason,
        )
