"""全部 Pydantic v2 数据契约（先定契约，再写实现）。

任何 Agent 不得自行发明新的跨层传输结构。

变更记录：
- v0.1.0 初始版本：Ticker / MarketSnapshot / AnalystReport / DebateTurn /
  DebateRecord / TradeProposal / RiskAssessment / Decision / ExecutionFill /
  PerformanceMetrics / MemoryEntry。
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field


class Market(StrEnum):
    US = "US"
    HK = "HK"
    CN = "CN"
    CRYPTO = "CRYPTO"


class Ticker(BaseModel):
    """标的身份（由 resolve_identity 节点确定性解析固定）。"""

    symbol: str
    market: Market = Market.US
    name: str = ""
    industry: str = ""
    currency: str = "USD"


class OHLCVBar(BaseModel):
    date: dt.date
    open: float
    high: float
    low: float
    close: float
    volume: int


class MarketSnapshot(BaseModel):
    """截至 ``as_of_date`` 的已验证数据快照（防未来函数的唯一数据入口）。"""

    ticker: Ticker
    as_of_date: dt.date  # 快照截止日期，必须 <= trade_date
    bars: list[OHLCVBar] = Field(default_factory=list)  # 按日期升序
    last_close: float
    market_cap: float | None = None
    index: str = ""  # 所属基准指数
    fundamentals: dict[str, float | str] = Field(default_factory=dict)
    news: list[str] = Field(default_factory=list)  # 截至 as_of_date 的新闻标题

    @property
    def last_bar(self) -> OHLCVBar | None:
        return self.bars[-1] if self.bars else None


class KeyFinding(BaseModel):
    claim: str
    evidence: str  # 必须引用数据快照字段或新闻条目
    source: str  # 如 "MarketSnapshot.bars", "snapshot.news[0]"


class AnalystReport(BaseModel):
    """各分析维度的通用报告结构。"""

    dimension: str  # fundamental / sentiment / news / technical
    ticker: str
    as_of_date: dt.date
    summary: str
    key_findings: list[KeyFinding] = Field(default_factory=list)
    score: float = 0.0  # -1(看空) ~ +1(看多)
    confidence: float = 0.5  # 0~1
    red_flags: list[str] = Field(default_factory=list)


class DebateTurn(BaseModel):
    round: int
    stance: str  # bull / bear
    argument: str
    response_to_opponent: str = ""  # 针对对方上轮论点的认同/反驳
    evidence: list[str] = Field(default_factory=list)


class DebateRecord(BaseModel):
    ticker: str
    as_of_date: dt.date
    turns: list[DebateTurn] = Field(default_factory=list)
    bull_summary: str = ""
    bear_summary: str = ""


class TradeAction(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class TradeProposal(BaseModel):
    ticker: str
    as_of_date: dt.date
    action: TradeAction
    position_pct: float = 0.0  # 目标仓位占组合比例 0~1
    entry_price: float | None = None  # 必须来自数据快照，None 表示市价
    stop_loss: float | None = None
    target_price: float | None = None
    holding_horizon: str = "swing"  # intraday / swing / position
    rationale: str = ""  # 必须引用具体报告/论点
    confidence: float = 0.5
    source_reports: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    max_drawdown_est: float = 0.0  # 估计最大回撤 0~1
    volatility_level: str = "medium"  # low / medium / high
    liquidity_concern: bool = False
    concentration_risk: str = "low"
    veto: bool = False  # 是否否决
    veto_reason: str = ""
    conditions: list[str] = Field(default_factory=list)  # 通过条件
    commentary: str = ""


class ApprovalStatus(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CONDITIONAL = "conditional"


class Decision(BaseModel):
    """最终决策对象：组合经理审批结果 + 理由链 + 全部中间产物引用。"""

    ticker: str
    trade_date: dt.date
    status: ApprovalStatus
    final_action: TradeAction
    final_position_pct: float = 0.0
    conditions: list[str] = Field(default_factory=list)
    rationale_chain: list[str] = Field(default_factory=list)  # 引用链
    proposal: TradeProposal | None = None
    risk: RiskAssessment | None = None
    artifact_refs: list[str] = Field(default_factory=list)  # 文件路径/记录 ID
    rejection_reason: str = ""


class ExecutionFill(BaseModel):
    ticker: str
    trade_date: dt.date
    action: TradeAction
    quantity: float
    price: float  # 含滑点的成交价
    reference_price: float  # 撮合基准价（快照收盘价）
    slippage: float
    commission: float
    settlement_date: dt.date  # T+1
    timestamp: dt.datetime


class PerformanceMetrics(BaseModel):
    total_return: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    sharpe: float = 0.0
    alpha: float = 0.0  # 相对基准
    beta: float = 0.0
    n_trades: int = 0
    benchmark: str = ""
    notes: str = ""


class MemoryEntry(BaseModel):
    """决策日志条目：决策 + 实现收益 + 反思段落。"""

    id: int | None = None
    ticker: str
    trade_date: dt.date
    action: TradeAction
    position_pct: float
    status: ApprovalStatus
    realized_return: float | None = None  # 后续实现收益（raw）
    alpha: float | None = None  # 相对基准
    reflection: str = ""
    decision_json: str = ""
    created_at: dt.datetime | None = None
