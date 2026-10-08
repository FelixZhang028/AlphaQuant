"""分析团队：基本面 / 情绪 / 新闻 / 技术四个分析师（机制 M1）。

每个分析师输入 MarketSnapshot，输出 AnalystReport。
技术面指标由本模块用 numpy 从快照 bar 序列**确定性计算**后提供给 LLM，
避免模型编造指标数值（机制 M8）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from trading_agents.agents.base import BaseAgent
from trading_agents.llm import LLMClient
from trading_agents.schemas import AnalystReport, MarketSnapshot

if TYPE_CHECKING:
    from trading_agents.orchestrator.events import AgentReporter


def compute_indicators(snapshot: MarketSnapshot) -> dict[str, float]:
    """从快照 bars 确定性计算常用技术指标。"""
    closes = np.array([b.close for b in snapshot.bars], dtype=float)
    volumes = np.array([b.volume for b in snapshot.bars], dtype=float)
    out: dict[str, float] = {}
    if len(closes) == 0:
        return out
    out["last_close"] = float(closes[-1])
    for w in (5, 20, 60):
        if len(closes) >= w:
            out[f"sma_{w}"] = float(np.mean(closes[-w:]))
    if len(closes) >= 2:
        out["return_5d"] = float(closes[-1] / closes[-min(6, len(closes))] - 1)
    # RSI(14)
    if len(closes) >= 15:
        diffs = np.diff(closes[-15:])
        gains = np.mean(np.clip(diffs, 0, None))
        losses = np.mean(np.clip(-diffs, 0, None))
        out["rsi_14"] = 100.0 if losses == 0 else float(100 - 100 / (1 + gains / losses))
    # MACD(12,26,9)
    if len(closes) >= 26:
        def ema(x: np.ndarray, n: int) -> np.ndarray:
            alpha = 2 / (n + 1)
            out_ema = np.empty_like(x)
            out_ema[0] = x[0]
            for i in range(1, len(x)):
                out_ema[i] = alpha * x[i] + (1 - alpha) * out_ema[i - 1]
            return out_ema
        macd_line = ema(closes, 12) - ema(closes, 26)
        signal = ema(macd_line, 9)
        out["macd"] = float(macd_line[-1])
        out["macd_signal"] = float(signal[-1])
    if len(volumes) >= 20:
        out["vol_ratio_20"] = float(volumes[-1] / max(np.mean(volumes[-20:]), 1))
    return {k: round(v, 6) for k, v in out.items()}


def snapshot_context(snapshot: MarketSnapshot) -> str:
    """把快照渲染为 Agent 可读的确定性上下文（含机器可读锚点行）。"""
    lines = [
        f"ticker={snapshot.ticker.symbol}",
        f"trade_date={snapshot.as_of_date.isoformat()}",
        f"last_close={snapshot.last_close}",
        f"标的名称: {snapshot.ticker.name}，行业: {snapshot.ticker.industry}，"
        f"货币: {snapshot.ticker.currency}，基准指数: {snapshot.index}",
        f"快照截止日期 as_of_date={snapshot.as_of_date.isoformat()}（禁止引用此日期之后的信息）",
        f"市值: {snapshot.market_cap}",
        f"财务字段: {snapshot.fundamentals}",
        f"技术指标(确定性计算): {compute_indicators(snapshot)}",
        "最近5个交易日: "
        + "; ".join(f"{b.date} C={b.close} V={b.volume}" for b in snapshot.bars[-5:]),
        "新闻条目: " + (" | ".join(snapshot.news) if snapshot.news else "（无）"),
    ]
    if snapshot.prior_knowledge.strip():
        lines.insert(
            3,
            "专家先验知识（用户/外部观点，务必优先参考）:\n" + snapshot.prior_knowledge,
        )
    return "\n".join(lines)


class _Analyst(BaseAgent):
    dimension: str = ""

    def analyze(self, snapshot: MarketSnapshot) -> AnalystReport:
        return self.ask(snapshot_context(snapshot), AnalystReport)  # type: ignore[return-value]


class FundamentalAnalyst(_Analyst):
    tag = "fundamental"
    prompt_file = "fundamental_analyst"
    dimension = "fundamental"


class SentimentAnalyst(_Analyst):
    tag = "sentiment"
    prompt_file = "sentiment_analyst"
    dimension = "sentiment"


class NewsAnalyst(_Analyst):
    tag = "news"
    prompt_file = "news_analyst"
    dimension = "news"


class TechnicalAnalyst(_Analyst):
    tag = "technical"
    prompt_file = "technical_analyst"
    dimension = "technical"


def run_analyst_team(
    llm: LLMClient,
    snapshot: MarketSnapshot,
    reporter: AgentReporter | None = None,
    dimensions: list[str] | None = None,
) -> dict[str, AnalystReport]:
    """并行维度入口（当前为顺序实现，接口与结果与并行一致）。

    返回 ``{dimension: AnalystReport}``；``dimensions`` 可筛选运行的维度
    （None 表示全部四个）。``reporter`` 为可选的 agent 级进度回调。
    """
    team: list[_Analyst] = [
        FundamentalAnalyst(llm),
        SentimentAnalyst(llm),
        NewsAnalyst(llm),
        TechnicalAnalyst(llm),
    ]
    if dimensions is not None:
        team = [a for a in team if a.dimension in dimensions]
    out: dict[str, AnalystReport] = {}
    for a in team:
        if reporter:
            reporter(a.dimension, "in_progress", None)
        report = a.analyze(snapshot)
        out[a.dimension] = report
        if reporter:
            reporter(a.dimension, "completed", report)
    return out
