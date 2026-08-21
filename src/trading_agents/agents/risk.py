"""风控团队：独立评估提案风险，输出 RiskAssessment（机制 M4）。"""

from __future__ import annotations

from trading_agents.agents.base import BaseAgent
from trading_agents.schemas import MarketSnapshot, RiskAssessment, TradeProposal


class RiskTeam(BaseAgent):
    tag = "risk"
    prompt_file = "risk_team"

    def assess(self, snapshot: MarketSnapshot, proposal: TradeProposal) -> RiskAssessment:
        content = (
            f"ticker={snapshot.ticker.symbol}\n"
            f"trade_date={snapshot.as_of_date.isoformat()}\n"
            f"last_close={snapshot.last_close}\n"
            f"交易提案: {proposal.model_dump_json()}\n"
            f"最近波动参考（最近5日收盘）: {[b.close for b in snapshot.bars[-5:]]}"
        )
        return self.ask(content, RiskAssessment)  # type: ignore[return-value]
