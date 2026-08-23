"""Trader：综合分析报告与辩论记录，输出 TradeProposal（机制 M3）。

历史决策与反思（记忆闭环，机制 M6）通过 ``memory_context`` 注入提示词。
"""

from __future__ import annotations

from trading_agents.agents.base import BaseAgent
from trading_agents.schemas import (
    AnalystReport,
    DebateRecord,
    MarketSnapshot,
    TradeProposal,
)


class Trader(BaseAgent):
    tag = "trader"
    prompt_file = "trader"

    def propose(
        self,
        snapshot: MarketSnapshot,
        reports: dict[str, AnalystReport],
        debate: DebateRecord,
        memory_context: str = "",
    ) -> TradeProposal:
        reports_txt = "\n".join(
            f"- [{r.dimension}] score={r.score} summary={r.summary} findings="
            f"{[f.claim for f in r.key_findings]}"
            for r in reports.values()
        )
        debate_txt = "\n".join(
            f"第{t.round}轮 [{t.stance}] 论点: {t.argument} | 回应: {t.response_to_opponent}"
            for t in debate.turns
        )
        content = (
            f"ticker={snapshot.ticker.symbol}\n"
            f"trade_date={snapshot.as_of_date.isoformat()}\n"
            f"last_close={snapshot.last_close}\n"
        )
        if snapshot.prior_knowledge.strip():
            content += f"\n专家先验知识（务必参考）:\n{snapshot.prior_knowledge}\n"
        content += (
            f"分析报告:\n{reports_txt}\n\n辩论记录:\n{debate_txt}\n"
            f"多方总结: {debate.bull_summary}\n空方总结: {debate.bear_summary}\n"
        )
        if memory_context:
            content += f"\n历史决策与反思（务必参考）:\n{memory_context}\n"
        return self.ask(content, TradeProposal)  # type: ignore[return-value]
