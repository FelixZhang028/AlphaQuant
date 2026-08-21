"""标准决策流水线（机制 M1-M8 的编排落地）。

节点序列：
resolve_identity → fetch_data → analyst_team → debate → trader_proposal
→ risk_review → pm_approval → execute(条件边) → record_memory

每个节点执行后写 checkpoint 与 trace；LLM 结构化输出失败计入
``max_llm_retries`` 重试预算，耗尽中止并记录原因。
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, Field

from trading_agents.agents import (
    PortfolioManager,
    RiskTeam,
    Trader,
    run_analyst_team,
    run_debate,
)
from trading_agents.config import TradingConfig
from trading_agents.data.base import DataProvider, validate_snapshot
from trading_agents.data.names import apply_name_fallback
from trading_agents.data.stub import StubDataProvider
from trading_agents.execution import Portfolio, SimulatedExchange
from trading_agents.llm import LLMClient, StructuredOutputError
from trading_agents.memory import MemoryStore
from trading_agents.orchestrator.events import AgentReporter, EventBus  # noqa: F401 - 签名使用
from trading_agents.orchestrator.machine import CheckpointStore, Node, StateMachine
from trading_agents.schemas import (
    AnalystReport,
    DebateRecord,
    Decision,
    ExecutionFill,
    MarketSnapshot,
    RiskAssessment,
    Ticker,
    TradeProposal,
)
from trading_agents.schemas.models import ApprovalStatus
from trading_agents.utils import TraceWriter, get_logger, retry

log = get_logger(__name__)

OUTCOME_HORIZON_DAYS = 5  # 记忆回填实现收益的观察窗口


class PipelineState(BaseModel):
    """流水线全局状态（checkpoint 序列化的对象）。"""

    run_id: str
    symbol: str
    trade_date: dt.date
    market: str = "US"
    identity: Ticker | None = None
    snapshot: MarketSnapshot | None = None
    reports: dict[str, AnalystReport] = Field(default_factory=dict)
    debate: DebateRecord | None = None
    proposal: TradeProposal | None = None
    risk: RiskAssessment | None = None
    decision: Decision | None = None
    fill: ExecutionFill | None = None
    memory_context: str = ""
    artifacts: list[str] = Field(default_factory=list)
    error: str = ""


@dataclass
class TokenLedger:
    """跨节点累计 token 消耗（写入 trace）。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class PipelineContext:
    """注入各节点的共享服务。"""

    config: TradingConfig
    llm: LLMClient
    provider: DataProvider
    memory: MemoryStore
    exchange: SimulatedExchange
    portfolio: Portfolio = field(default_factory=Portfolio)
    token_ledger: TokenLedger = field(default_factory=TokenLedger)
    agent_reporter: AgentReporter | None = None  # agent 级进度回调（TUI 用）


# ------------------------------------------------------------ 节点实现 ----

def _node_resolve_identity(state: PipelineState, ctx: PipelineContext) -> None:
    ticker = ctx.provider.resolve(state.symbol, state.market)
    # 数据源名称不可用（stub 占位 / yfinance 限流降级）时，用内置映射表兜底，
    # 保证后续分析/辩论阶段能输出可读的标的名称（如 688836.SS → 宇树科技）。
    ticker.name = apply_name_fallback(state.symbol, ticker.name)
    state.identity = ticker


def _node_fetch_data(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.identity is not None
    try:
        snapshot = ctx.provider.get_snapshot(state.identity, state.trade_date)
    except RuntimeError as exc:
        # yfinance 网络失败且无缓存时自动降级 stub，避免流水线中断；
        # 仅当数据源非 stub 时才降级（stub 自身失败直接抛错）。
        if ctx.provider.name != "stub":
            log.warning(
                "数据源 %s 获取 %s 行情失败（%s），自动降级 stub 数据源",
                ctx.provider.name, state.symbol, exc,
            )
            snapshot = StubDataProvider().get_snapshot(state.identity, state.trade_date)
        else:
            raise
    state.snapshot = validate_snapshot(snapshot, state.trade_date)  # 防未来函数
    _backfill_outcomes(state, ctx)


def _backfill_outcomes(state: PipelineState, ctx: PipelineContext) -> None:
    """用最新数据回填历史决策的实现收益与反思（记忆闭环前置步骤）。"""
    for entry in ctx.memory.history(state.symbol, limit=5):
        if entry.realized_return is not None or entry.trade_date >= state.trade_date:
            continue
        try:
            entry_price = _entry_price_of(entry.decision_json)
            bars = ctx.provider.get_bars_after(
                state.identity, entry.trade_date, OUTCOME_HORIZON_DAYS  # type: ignore[arg-type]
            )
        except Exception as exc:  # noqa: BLE001 - 回填失败不阻塞主流程，但记日志
            log.warning("实现收益回填失败（%s）: %s", entry.trade_date, exc)
            continue
        if entry_price and bars:
            realized = bars[-1].close / entry_price - 1
            if entry.action.value == "sell":
                realized = -realized
            ctx.memory.update_outcome(state.symbol, realized, None)


def _entry_price_of(decision_json: str) -> float | None:
    try:
        data = json.loads(decision_json)
        proposal = data.get("proposal") or {}
        return proposal.get("entry_price")
    except (json.JSONDecodeError, AttributeError):
        return None


def _llm_retry(fn, ctx: PipelineContext):
    """LLM 结构化调用重试包装：失败计入 max_llm_retries，耗尽抛错中止。"""
    return retry(
        fn,
        max_attempts=ctx.config.max_llm_retries,
        exceptions=(StructuredOutputError,),
    )


def _node_analyst_team(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.snapshot is not None
    state.reports = _llm_retry(
        lambda: run_analyst_team(
            ctx.llm, state.snapshot,  # type: ignore[arg-type]
            reporter=ctx.agent_reporter, dimensions=ctx.config.analyst_dims,
        ),
        ctx,
    )


def _node_debate(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.snapshot is not None
    state.debate = _llm_retry(
        lambda: run_debate(  # type: ignore[arg-type]
            ctx.llm,
            state.snapshot,
            state.reports,
            ctx.config.debate_rounds,
            reporter=ctx.agent_reporter,
        ),
        ctx,
    )


def _report(ctx: PipelineContext, agent: str, status: str, payload: object = None) -> None:
    """agent 级进度上报（未订阅时为空操作）。"""
    if ctx.agent_reporter is not None:
        ctx.agent_reporter(agent, status, payload)


def _node_trader_proposal(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.snapshot is not None and state.debate is not None
    state.memory_context = ctx.memory.context_for(state.symbol)
    trader = Trader(ctx.llm)
    _report(ctx, "trader", "in_progress")
    state.proposal = _llm_retry(
        lambda: trader.propose(state.snapshot, state.reports, state.debate, state.memory_context),  # type: ignore[arg-type]
        ctx,
    )
    _report(ctx, "trader", "completed", state.proposal)
    _acc_tokens(ctx, trader)


def _node_risk_review(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.snapshot is not None and state.proposal is not None
    team = RiskTeam(ctx.llm)
    _report(ctx, "risk", "in_progress")
    state.risk = _llm_retry(lambda: team.assess(state.snapshot, state.proposal), ctx)  # type: ignore[arg-type]
    _report(ctx, "risk", "completed", state.risk)
    _acc_tokens(ctx, team)


def _node_pm_approval(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.snapshot is not None and state.proposal is not None and state.risk is not None
    pm = PortfolioManager(ctx.llm)
    _report(ctx, "pm", "in_progress")
    state.decision = _llm_retry(
        lambda: pm.decide(state.snapshot, state.proposal, state.risk), ctx  # type: ignore[arg-type]
    )
    _report(ctx, "pm", "completed", state.decision)
    _acc_tokens(ctx, pm)
    path = _dump_decision_artifact(ctx, state)
    state.decision.artifact_refs.append(str(path))


def _execute_condition(state: PipelineState) -> bool:
    return state.decision is not None and state.decision.status != ApprovalStatus.REJECTED


def _node_execute(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.snapshot is not None and state.decision is not None
    state.fill = ctx.exchange.execute(state.decision, state.snapshot, ctx.portfolio)
    if state.fill is not None:
        _dump_artifact(ctx, state, "fill", state.fill)


def _node_record_memory(state: PipelineState, ctx: PipelineContext) -> None:
    assert state.decision is not None
    ctx.memory.record(state.decision)


# ------------------------------------------------------------ 工具 ----

def _acc_tokens(ctx: PipelineContext, agent) -> None:
    resp = getattr(agent, "last_response", None)
    if resp is not None:
        ctx.token_ledger.prompt_tokens += resp.prompt_tokens
        ctx.token_ledger.completion_tokens += resp.completion_tokens


def _dump_artifact(ctx: PipelineContext, state: PipelineState, kind: str, model: BaseModel) -> Path:
    path = ctx.config.artifacts_dir / f"{state.run_id}_{kind}.json"
    path.write_text(model.model_dump_json(indent=2), encoding="utf-8")
    state.artifacts.append(str(path))
    return path


def _dump_decision_artifact(ctx: PipelineContext, state: PipelineState) -> Path:
    """写决策产物 JSON：保留决策摘要全部字段，追加分析报告与辩论全文。

    顶层即 Decision 平铺字段（与旧格式兼容），并追加 ``identity``、
    ``reports``（4 维度分析报告）与 ``debate``（多轮多空辩论全文），
    使每次运行结束可直接从产物文件查看完整分析过程。
    """
    payload: dict = state.decision.model_dump(mode="json")  # type: ignore[union-attr]
    if state.identity is not None:
        payload["identity"] = state.identity.model_dump(mode="json")
    payload["reports"] = {
        k: r.model_dump(mode="json") for k, r in (state.reports or {}).items()
    }
    payload["debate"] = (
        state.debate.model_dump(mode="json") if state.debate is not None else None
    )
    path = ctx.config.artifacts_dir / f"{state.run_id}_decision.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    state.artifacts.append(str(path))
    return path


def build_pipeline() -> list[Node]:
    """标准节点序列（execute 带条件边：被驳回则跳过）。"""
    return [
        Node("resolve_identity", _node_resolve_identity),
        Node("fetch_data", _node_fetch_data),
        Node("analyst_team", _node_analyst_team),
        Node("debate", _node_debate),
        Node("trader_proposal", _node_trader_proposal),
        Node("risk_review", _node_risk_review),
        Node("pm_approval", _node_pm_approval),
        Node("execute", _node_execute, condition=_execute_condition),
        Node("record_memory", _node_record_memory),
    ]


def run_pipeline(
    symbol: str,
    trade_date: dt.date,
    ctx: PipelineContext,
    run_id: str | None = None,
    resume: bool = True,
    event_bus: EventBus | None = None,
) -> PipelineState:
    """端到端执行一次决策流水线。``resume=True`` 时从 checkpoint 断点续跑。

    ``event_bus`` 为可选的事件订阅通道：每节点开始/完成时发出 NodeEvent。
    """
    run_id = run_id or f"{symbol.upper()}_{trade_date.isoformat()}"
    state = PipelineState(run_id=run_id, symbol=symbol.upper(), trade_date=trade_date,
                          market=ctx.config.market)
    tracer = TraceWriter(ctx.config.trace_dir, run_id)
    ckpt = CheckpointStore(ctx.config.sqlite_path) if ctx.config.checkpoint_enabled else None
    machine = StateMachine(
        build_pipeline(), state, ctx, run_id, tracer,
        checkpoint=ckpt, node_retries=ctx.config.node_retries, debug=ctx.config.debug,
        event_bus=event_bus,
    )
    if resume and ckpt is not None:
        machine.restore(PipelineState)
    try:
        return machine.run()
    except RuntimeError as exc:
        machine.state.error = str(exc)
        if ckpt is not None:
            ckpt.save(run_id, machine.state, machine.completed)
        log.error("流水线中止: %s", exc)
        raise
    finally:
        if ckpt is not None:
            ckpt.close()
