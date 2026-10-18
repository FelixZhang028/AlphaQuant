"""多空研究员结构化辩论（机制 M2）。

流程：双方初始观点 → ``rounds`` 轮交锋（每轮必须针对对方上一轮论点
给出认同/反驳 + 证据）→ 双方总结立场。全程落盘为 DebateRecord。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from trading_agents.agents.base import BaseAgent
from trading_agents.schemas import AnalystReport, DebateRecord, DebateTurn, MarketSnapshot

if TYPE_CHECKING:
    from trading_agents.orchestrator.events import AgentReporter


class DebaterOutput(BaseModel):
    """辩手单轮输出的 LLM 侧契约。"""

    argument: str
    response_to_opponent: str = ""
    evidence: list[str] = Field(default_factory=list)


def _reports_digest(reports: dict[str, AnalystReport]) -> str:
    return "\n".join(
        f"- [{r.dimension}] score={r.score} confidence={r.confidence} summary={r.summary}"
        + (f" red_flags={r.red_flags}" if r.red_flags else "")
        for r in reports.values()
    )


class _Researcher(BaseAgent):
    stance: str = ""

    def argue(
        self,
        round_no: int,
        snapshot: MarketSnapshot,
        reports: dict[str, AnalystReport],
        opponent_last: DebateTurn | None,
    ) -> DebaterOutput:
        opponent = (
            f"对方（{'看空' if self.stance == 'bull' else '看多'}）上轮论点: "
            f"{opponent_last.argument}" if opponent_last else "对方尚未发言（本轮为开局立论）。"
        )
        content = (
            f"ticker={snapshot.ticker.symbol}\n"
            f"标的名称: {snapshot.ticker.name}\n"
            f"trade_date={snapshot.as_of_date.isoformat()}\n"
            f"last_close={snapshot.last_close}\n"
            f"当前轮次: 第 {round_no} 轮。\n{opponent}\n"
            f"分析团队报告:\n{_reports_digest(reports)}"
        )
        return self.ask(content, DebaterOutput)  # type: ignore[return-value]


class BullResearcher(_Researcher):
    tag = "bull"
    prompt_file = "bull_researcher"
    stance = "bull"


class BearResearcher(_Researcher):
    tag = "bear"
    prompt_file = "bear_researcher"
    stance = "bear"


def run_debate(
    llm,
    snapshot: MarketSnapshot,
    reports: dict[str, AnalystReport],
    rounds: int = 2,
    reporter: AgentReporter | None = None,
) -> DebateRecord:
    """执行 ``rounds`` 轮多空辩论，返回完整 DebateRecord。

    ``reporter`` 为可选的 agent 级进度回调（TUI 实时状态用）。
    """
    bull, bear = BullResearcher(llm), BearResearcher(llm)
    record = DebateRecord(
        ticker=snapshot.ticker.symbol, as_of_date=snapshot.as_of_date
    )
    last_bull: DebateTurn | None = None
    last_bear: DebateTurn | None = None
    for r in range(1, rounds + 1):
        if reporter:
            reporter("bull", "in_progress", None)
        b_out = bull.argue(r, snapshot, reports, last_bear)
        last_bull = DebateTurn(
            round=r, stance="bull", argument=b_out.argument,
            response_to_opponent=b_out.response_to_opponent, evidence=b_out.evidence,
        )
        record.turns.append(last_bull)
        if reporter:
            reporter("bull", "completed", last_bull)
        if reporter:
            reporter("bear", "in_progress", None)
        s_out = bear.argue(r, snapshot, reports, last_bull)
        last_bear = DebateTurn(
            round=r, stance="bear", argument=s_out.argument,
            response_to_opponent=s_out.response_to_opponent, evidence=s_out.evidence,
        )
        record.turns.append(last_bear)
        if reporter:
            reporter("bear", "completed", last_bear)
    record.bull_summary = last_bull.argument if last_bull else ""
    record.bear_summary = last_bear.argument if last_bear else ""
    return record
