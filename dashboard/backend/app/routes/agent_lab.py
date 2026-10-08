"""智能体分析台路由（真实 LLM 多智能体流水线，迁移自 AlphaQuant）。

以 vendored trading_agents 框架为核心：本地行情（Parquet）喂给
DataFrameProvider，先验知识注入各 Agent 提示词；默认 mock provider
可离线跑通全流程，也可配置 OpenAI 兼容的真实模型。

每个用户的运行时数据（LLM 设置 / 先验知识 / 流水线运行目录 / 决策缓存）
相互隔离，存放于 data/runtime/agent_lab/user_{id}/。
"""

from __future__ import annotations

import re
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field


def _sanitize_detail(exc: Exception) -> str:
    """清洗异常信息，去除技术细节，只保留用户可读消息。"""
    text = str(exc).strip()
    if not text:
        return "操作失败，请检查输入或稍后重试"
    text = re.sub(r"^[A-Z]\w*(?:Error|Exception|Warning|Interrupt):\s*", "", text)
    text = re.sub(r"^[A-Z][A-Z_]{2,}:\s*", "", text)
    text = re.sub(r'File ["\'][^"\']+["\'],\s*line\s*\d+[^)]*', "", text)
    text = re.sub(r"[\w./\\-]+\.py:\d+:\s*", "", text)
    if "Traceback" in text:
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("Traceback") and not l.startswith('  File')]
        text = lines[-1] if lines else ""
    text = text.strip()
    if not text or len(text) < 2:
        return "操作失败，请检查输入或稍后重试"
    return text

from quant_platform.agents_bridge.llm_settings import (
    PROVIDER_CATALOG,
    LLMSettingsStore,
)
from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.agents_bridge.runner import AgentRunner
from quant_platform.agents_bridge.sources import NEWS_SOURCES, STOCK_SOURCES
from trading_agents.orchestrator.events import EventBus

from ..quant.runtime import BACKEND_ROOT, market_repository, security_names
from ..quant.symbols import to_bare, to_canonical
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/agent-lab", tags=["agent-lab"])

_AGENT_ROOT = BACKEND_ROOT / "data" / "runtime" / "agent_lab"

_NODE_LABELS = {
    "resolve_identity": "标的识别",
    "fetch_data": "数据获取",
    "analyst_team": "分析师团队",
    "debate": "多空辩论",
    "trader_proposal": "交易员提案",
    "risk_review": "风控审核",
    "pm_approval": "组合经理审批",
    "execute": "模拟成交",
    "record_memory": "记忆归档",
}
_STATUS_LABELS = {"approved": "批准", "rejected": "拒绝", "conditional": "有条件批准"}
_ACTION_LABELS = {"buy": "买入", "sell": "卖出", "hold": "持有"}
_ANALYST_LABELS = {
    "fundamental": "基本面",
    "sentiment": "情绪面",
    "news": "新闻舆情",
    "technical": "技术面",
}

# 每用户最近一次分析的运行器与上下文（供「与 AI 对话交锋」复用）。
_RUN_LOCK = threading.Lock()
_LAST_RUN: dict[int, dict[str, Any]] = {}


def _user_dir(user_id: int) -> Path:
    path = _AGENT_ROOT / f"user_{user_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _llm_store(user_id: int) -> LLMSettingsStore:
    return LLMSettingsStore(_user_dir(user_id) / "llm_settings.json")


def _prior_store(user_id: int) -> PriorKnowledgeStore:
    return PriorKnowledgeStore(_user_dir(user_id) / "prior_knowledge.json")


def _provider_payload(store: LLMSettingsStore, provider: str) -> dict[str, Any]:
    spec = PROVIDER_CATALOG.get(provider)
    if spec is None:
        return {}
    resolved = store.resolve(provider)
    return {
        "key": spec.key,
        "display_name": spec.display_name,
        "requires_key": spec.requires_key,
        "default_base_url": spec.default_base_url,
        "models": list(spec.models),
        "default_model": spec.default_model,
        "base_url": resolved["base_url"],
        "api_key": bool(resolved["api_key"]),
        "model": resolved["model"],
    }


# --------------------------------------------------------------------------- #
# 配置
# --------------------------------------------------------------------------- #


@router.get("/config", summary="智能体分析台配置")
def agent_config(user: dict = Depends(get_current_user)):
    store = _llm_store(user["id"])
    provider = store.get_default_provider()
    if provider == "openrouter":
        provider = "mock"
    entries = _prior_store(user["id"]).list()
    return {
        "default_provider": provider,
        "providers": [
            _provider_payload(store, key) for key in PROVIDER_CATALOG if key != "openrouter"
        ],
        "stock_sources": [
            {"key": key, "label": label} for key, label in STOCK_SOURCES.items()
        ],
        "news_sources": [
            {"key": key, "label": label} for key, label in NEWS_SOURCES.items()
        ],
        "prior_knowledge": [entry.to_dict() for entry in entries],
    }


class ProviderSaveIn(BaseModel):
    provider: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@router.post("/config", summary="保存 LLM Provider 配置（仅存本地）")
def agent_config_save(body: ProviderSaveIn, user: dict = Depends(get_current_user)):
    if body.provider not in PROVIDER_CATALOG or body.provider == "openrouter":
        raise HTTPException(status_code=422, detail="未知的 LLM 提供商")
    store = _llm_store(user["id"])
    store.save(
        body.provider,
        base_url=body.base_url.strip(),
        api_key=body.api_key.strip() or store.get(body.provider)["api_key"],
        model=body.model.strip(),
    )
    store.save_default_provider(body.provider)
    return {"ok": True, "message": "已保存到本地配置（仅保存在本机，不会上传）"}


# --------------------------------------------------------------------------- #
# 先验知识库
# --------------------------------------------------------------------------- #


class PriorAddIn(BaseModel):
    content: str = Field(..., min_length=2, max_length=2000)
    source: str = ""


@router.get("/prior-knowledge", summary="先验知识列表")
def prior_list(user: dict = Depends(get_current_user)):
    entries = _prior_store(user["id"]).list()
    return {"entries": [entry.to_dict() for entry in entries]}


@router.post("/prior-knowledge", status_code=status.HTTP_201_CREATED, summary="新增先验知识")
def prior_add(body: PriorAddIn, user: dict = Depends(get_current_user)):
    try:
        entry = _prior_store(user["id"]).add(body.content, body.source)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc)) from exc
    return entry.to_dict()


@router.delete(
    "/prior-knowledge/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除先验知识",
)
def prior_delete(entry_id: str, user: dict = Depends(get_current_user)):
    _prior_store(user["id"]).delete(entry_id)


# --------------------------------------------------------------------------- #
# 运行分析（真实流水线）
# --------------------------------------------------------------------------- #


class AgentRunIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)
    trade_date: str = ""
    lookback_days: int = Field(60, ge=20, le=250)
    debate_rounds: int = Field(1, ge=0, le=4)
    provider: str = "mock"
    stock_source: str = "local"
    news_sources: list[str] = Field(default_factory=list)
    prior_ids: list[str] | None = None  # None = 注入全部
    use_cache: bool = True


def _enum_text(value: object) -> str:
    return str(getattr(value, "value", value))


def _history_frame(symbol: str, end: date, lookback: int) -> pd.DataFrame:
    frame = market_repository().get_daily_bars(symbols=[symbol], end_date=end)
    if frame.empty:
        return frame
    return frame.sort_values("trade_date").tail(lookback).reset_index(drop=True)


def _state_to_json(state, decision) -> dict[str, Any]:
    """把 PipelineState / Decision 压成前端展示结构。"""

    proposal = state.proposal if state is not None else None
    if proposal is None and decision.proposal is not None:
        proposal = decision.proposal

    analysts = []
    if state is not None and state.reports:
        for dimension, report in state.reports.items():
            analysts.append(
                {
                    "dimension": _ANALYST_LABELS.get(dimension, dimension),
                    "score": report.score,
                    "confidence": report.confidence,
                    "summary": report.summary,
                    "key_findings": [f.claim for f in report.key_findings],
                    "risks": list(report.red_flags),
                }
            )

    debate = []
    if state is not None and state.debate is not None:
        by_round: dict[int, dict[str, str]] = {}
        for turn in state.debate.turns:
            slot = by_round.setdefault(turn.round, {"round": turn.round})
            if turn.stance == "bull":
                slot["bull"] = turn.argument
                if turn.response_to_opponent:
                    slot["bull_reply"] = turn.response_to_opponent
            else:
                slot["bear"] = turn.argument
                if turn.response_to_opponent:
                    slot["bear_reply"] = turn.response_to_opponent
        debate = sorted(by_round.values(), key=lambda item: item["round"])
        if debate:
            if state.debate.bull_summary:
                debate[-1]["bull_summary"] = state.debate.bull_summary
            if state.debate.bear_summary:
                debate[-1]["bear_summary"] = state.debate.bear_summary

    proposal_json = {}
    if proposal is not None:
        proposal_json = {
            "action": _ACTION_LABELS.get(_enum_text(proposal.action), _enum_text(proposal.action)),
            "position_pct": round(float(proposal.position_pct) * 100, 1),
            "confidence": proposal.confidence,
            "stop_loss": proposal.stop_loss,
            "target_price": proposal.target_price,
            "holding_period": proposal.holding_horizon,
            "reason": proposal.rationale,
        }

    risk = state.risk if state is not None else decision.risk
    risk_json = {}
    if risk is not None:
        risk_json = {
            "vetoed": risk.veto,
            "volatility": risk.volatility_level,
            "est_max_drawdown": f"-{round(float(risk.max_drawdown_est) * 100, 1)}%",
            "veto_reason": risk.veto_reason or None,
            "conditions": list(risk.conditions),
            "comment": risk.commentary,
        }

    fill_json = {}
    if state is not None and state.fill is not None:
        fill_json = {
            "action": _ACTION_LABELS.get(_enum_text(state.fill.action), _enum_text(state.fill.action)),
            "quantity": round(float(state.fill.quantity)),
            "price": state.fill.price,
            "benchmark_price": state.fill.reference_price,
            "fee": state.fill.commission,
            "settle": str(state.fill.settlement_date),
        }

    return {
        "decision": {
            "status": _STATUS_LABELS.get(_enum_text(decision.status), _enum_text(decision.status)),
            "final_action": _ACTION_LABELS.get(
                _enum_text(decision.final_action), _enum_text(decision.final_action)
            ),
            "final_position_pct": round(float(decision.final_position_pct) * 100, 1),
            "confidence": proposal.confidence if proposal is not None else None,
            "rejection_reason": decision.rejection_reason or None,
            "conditions": list(decision.conditions),
            "rationale_chain": list(decision.rationale_chain),
        },
        "state": {
            "analysts": analysts,
            "debate": debate,
            "proposal": proposal_json,
            "risk": risk_json,
            "fill": fill_json,
            "error": state.error if state is not None else "",
        },
    }


def _battle_context(state, decision, prior_text: str, name: str) -> str:
    lines = [
        f"标的: {decision.ticker}（{name}）",
        f"分析日期: {decision.trade_date}",
        "最终决策: "
        f"{_enum_text(decision.status)} / {_enum_text(decision.final_action)} / "
        f"仓位 {float(decision.final_position_pct):.1%}",
    ]
    if decision.rationale_chain:
        lines.append("理由链: " + "；".join(str(item) for item in decision.rationale_chain))
    if decision.rejection_reason:
        lines.append(f"拒绝原因: {decision.rejection_reason}")
    if prior_text.strip():
        lines.append(f"用户设定的先验知识（分析时的约束边界）:\n{prior_text}")
    if state is not None:
        if state.reports:
            for dimension, report in state.reports.items():
                label = _ANALYST_LABELS.get(dimension, dimension)
                lines.append(f"[{label}] 评分 {float(report.score):+.2f}：{report.summary}")
        if state.debate is not None:
            if state.debate.bull_summary:
                lines.append(f"多方总结: {state.debate.bull_summary}")
            if state.debate.bear_summary:
                lines.append(f"空方总结: {state.debate.bear_summary}")
        if state.proposal is not None and state.proposal.rationale:
            lines.append(f"提案理由: {state.proposal.rationale}")
    return "\n".join(lines)


@router.post("/run", summary="运行多智能体分析流水线（真实引擎）")
def agent_run(body: AgentRunIn, user: dict = Depends(get_current_user)):
    if body.provider not in PROVIDER_CATALOG or body.provider == "openrouter":
        raise HTTPException(status_code=422, detail="未知的 LLM 提供商")
    store = _llm_store(user["id"])
    resolved = store.resolve(body.provider)
    spec = PROVIDER_CATALOG[body.provider]
    if spec.requires_key and not resolved["api_key"]:
        raise HTTPException(
            status_code=422,
            detail=f"{spec.display_name} 未配置 API Key，请先在配置中填写，或改用 Mock 离线运行。",
        )
    if body.provider == "custom" and not resolved["base_url"]:
        raise HTTPException(status_code=422, detail="自定义端点需要填写 Base URL")

    symbol = to_canonical(body.symbol)
    try:
        trade_date = date.fromisoformat(body.trade_date) if body.trade_date else date.today()
    except ValueError:
        raise HTTPException(status_code=422, detail="分析日期格式无效") from None

    user_dir = _user_dir(user["id"])
    try:
        history = _history_frame(symbol, trade_date, int(body.lookback_days))
    except Exception as exc:  # noqa: BLE001 - 仓库读取异常统一转 422
        raise HTTPException(status_code=422, detail=f"读取行情数据失败：{_sanitize_detail(exc)}") from exc
    if history.empty:
        if body.stock_source == "local":
            raise HTTPException(
                status_code=422,
                detail=f"{symbol} 在 {trade_date} 及之前没有本地行情数据，请先在数据管理中下载行情，或改用在线行情源。",
            )
        history = history.iloc[0:0]

    prior_store = _prior_store(user["id"])
    prior_text = prior_store.render(body.prior_ids)

    runner = AgentRunner(
        llm_provider=body.provider,
        debate_rounds=int(body.debate_rounds),
        use_cache=body.use_cache,
        base_url=resolved["base_url"] or None,
        model=resolved["model"] or None,
        api_key=resolved["api_key"] or None,
        prior_knowledge=prior_text,
        stock_source=body.stock_source,
        news_sources=tuple(body.news_sources),
        base_dir=user_dir / "agent_runs",
        cache_dir=user_dir / "agent_cache",
    )

    trace_log: list[str] = []
    state = None
    try:
        if body.use_cache:
            decision = runner.decide(symbol, trade_date, history)
            trace_log = ["命中缓存或已完成流水线（勾选缓存时不记录中间过程）"]
        else:
            bus = EventBus()
            node_labels = dict(_NODE_LABELS)

            def _on_node(event, _state=None) -> None:
                label = node_labels.get(event.node, event.node)
                if event.kind == "started":
                    trace_log.append(f"{label} …")
                elif event.status == "error":
                    trace_log.append(f"{label} 失败：{event.error or '未知错误'}")
                else:
                    suffix = f"（{event.summary}）" if event.summary else ""
                    trace_log.append(f"{label} 完成{suffix}")

            bus.subscribe(_on_node)
            state = runner.decide_full(symbol, trade_date, history, event_bus=bus)
            decision = state.decision
    except Exception as exc:  # noqa: BLE001 - 流水线异常统一转 422
        raise HTTPException(status_code=422, detail=f"智能体分析运行失败：{_sanitize_detail(exc)}") from exc

    if decision is None:
        raise HTTPException(status_code=422, detail="流水线未产出决策")

    names = security_names()
    name = names.get(symbol) or names.get(to_bare(symbol)) or "名称未知"
    payload = _state_to_json(state, decision)
    context = _battle_context(state, decision, prior_text, name)
    with _RUN_LOCK:
        _LAST_RUN[user["id"]] = {
            "runner": runner,
            "context": context,
            "symbol": symbol,
            "name": name,
        }

    return {
        "run_id": state.run_id if state is not None else decision.ticker,
        "symbol": symbol,
        "name": name,
        "cached": state is None,
        **payload,
        "trace_log": trace_log,
    }


# --------------------------------------------------------------------------- #
# 与 AI 对话交锋
# --------------------------------------------------------------------------- #


class BattleIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[dict[str, str]] = Field(default_factory=list)


@router.post("/battle", summary="与 AI 对话交锋（带分析上下文）")
def agent_battle(body: BattleIn, user: dict = Depends(get_current_user)):
    with _RUN_LOCK:
        last = _LAST_RUN.get(user["id"])
    if last is None:
        return {
            "reply": "还没有可引用的分析结果。请先在上方「运行分析」完成一次智能体分析，"
            "再回来与 AI 交锋讨论。"
        }
    history = [
        (str(item.get("role", "user")), str(item.get("text", "")))
        for item in body.history
        if item.get("text")
    ]
    try:
        reply = last["runner"].battle(last["context"], body.message, history)
    except Exception as exc:  # noqa: BLE001 - LLM 异常统一转 422
        raise HTTPException(status_code=422, detail=f"对话失败：{_sanitize_detail(exc)}") from exc
    return {"reply": reply}
