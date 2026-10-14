"""AI 研究员路由：用本地数据读懂一只股票。

每次分析先从本地数据整理出这只股票当天的数据（价格走势、成交、全市场比较、估值、财报、
行业、指数、分红），这一步不需要 AI，也不限次数。平台配置了 AI 模型时，再让模型只根据这些
数据写出倾向和要点；检查不通过的要点会被去掉。每次结果都保存，可以打开和继续追问。

研究经验（先验知识）按用户隔离，存放于 data/runtime/agent_lab/user_{id}/。
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, status
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

from quant_platform.agents_bridge.llm_settings import LLMSettingsStore
from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.ai_research.brief import (
    BriefFormatError,
    ask_messages,
    brief_messages,
    check_answer,
    check_brief,
    parse_json,
    retry_messages,
)
from quant_platform.ai_research.facts import StockFacts, stock_facts

from ..database import get_conn
from ..quant import platform_ai
from ..quant.runtime import BACKEND_ROOT, market_repository, security_names
from ..quant.symbols import to_bare, to_canonical
from ..routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agent-lab", tags=["agent-lab"])

_AGENT_ROOT = BACKEND_ROOT / "data" / "runtime" / "agent_lab"
# 追问时带上最近几轮对话，太早的不再发给模型。
MAX_HISTORY = 6


def _user_dir(user_id: int) -> Path:
    path = _AGENT_ROOT / f"user_{user_id}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _llm_store(user_id: int) -> LLMSettingsStore:
    return LLMSettingsStore(_user_dir(user_id) / "llm_settings.json")


def _prior_store(user_id: int) -> PriorKnowledgeStore:
    return PriorKnowledgeStore(_user_dir(user_id) / "prior_knowledge.json")


def _ai_failure(exc: Exception) -> str:
    """模型调用失败时给用户看的原因。"""
    if isinstance(exc, requests.Timeout):
        return "AI 服务响应超时"
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code in (401, 403):
            return "平台的 AI 密钥无效，请联系管理员"
        if code == 402:
            return "平台的 AI 账户余额不足，请联系管理员"
        if code == 429:
            return "AI 服务繁忙，请稍后再试"
        return f"AI 服务返回错误（{code}）"
    if isinstance(exc, requests.RequestException):
        return "连接不上 AI 服务"
    if isinstance(exc, BriefFormatError):
        return f"AI 的回答格式不对：{exc}"
    return _sanitize_detail(exc)


# --------------------------------------------------------------------------- #
# 状态
# --------------------------------------------------------------------------- #


@router.get("/status", summary="AI 研究员：模型是否可用、今天还剩几次")
def agent_status(user: dict = Depends(get_current_user)):
    model = platform_ai.platform_model()
    bounds = market_repository().daily_bar_bounds()
    return {
        "ai": {"available": model is not None, "model": model.label if model else None},
        "usage": {kind: platform_ai.usage(user, kind) for kind in ("brief", "question")},
        "experience_count": len(_prior_store(user["id"]).list()),
        "latest_date": bounds[1].isoformat() if bounds else None,
    }


# --------------------------------------------------------------------------- #
# 研究经验
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
# 个股分析
# --------------------------------------------------------------------------- #


class BriefIn(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=12)
    trade_date: str = ""  # 空表示本地最新的交易日
    use_experience: bool = True


class QuestionIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=500)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(row) -> dict[str, Any]:
    stored = json.loads(row["brief"]) if row["brief"] else {}
    return {
        "id": row["id"],
        "symbol": row["symbol"],
        "name": row["name"],
        "trade_date": row["trade_date"],
        "created_at": row["created_at"],
        "model": row["model"] or None,
        "facts": json.loads(row["facts"]),
        "brief": stored.get("reading"),
        "ai_note": stored.get("note", ""),
        "use_experience": bool(stored.get("experience", False)),
        "questions": json.loads(row["questions"] or "[]"),
    }


def _load(brief_id: str, user: dict):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM stock_briefs WHERE id = ? AND user_id = ?", (brief_id, user["id"])).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="没有找到这次分析")
    return row


def _read_brief(model: platform_ai.PlatformModel, stock: StockFacts, experience: str) -> dict[str, Any]:
    """问一次模型；格式不对时把问题告诉它再问一次。"""
    client = platform_ai.model_client(model)
    messages = brief_messages(stock, experience)
    answer = client.chat(messages, temperature=0.2, max_tokens=1500).text
    try:
        return check_brief(parse_json(answer), stock)
    except BriefFormatError as exc:
        answer = client.chat(retry_messages(messages, answer, str(exc)), temperature=0.2, max_tokens=1500).text
        return check_brief(parse_json(answer), stock)


@router.post("/briefs", status_code=status.HTTP_201_CREATED, summary="分析一只股票：本地数据 + AI 解读")
def brief_create(body: BriefIn, user: dict = Depends(get_current_user)):
    symbol = to_canonical(body.symbol.strip())
    try:
        day = date.fromisoformat(body.trade_date) if body.trade_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="分析日期格式无效") from None
    names = security_names()
    name = names.get(symbol) or names.get(to_bare(symbol)) or symbol
    try:
        stock = stock_facts(market_repository(), symbol, day, name=name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc)) from exc

    experience = _prior_store(user["id"]).render(None) if body.use_experience else ""
    reading, model_label, note = None, "", ""
    model = platform_ai.platform_model()
    if model is None:
        note = "平台还没有配置 AI 模型，这次只显示数据。"
    else:
        try:
            platform_ai.require_quota(user, "brief")
            reading = _read_brief(model, stock, experience)
            platform_ai.record_use(user, "brief")
            model_label = model.label
        except platform_ai.QuotaExceeded as exc:
            note = f"{exc}下面的数据不受次数限制。"
        except Exception as exc:  # noqa: BLE001 - 模型失败时仍然给出数据
            logger.warning("AI brief failed for %s: %s", symbol, exc)
            note = f"AI 解读没有完成（{_ai_failure(exc)}），这次不计入次数。下面的数据仍然可以参考。"

    brief_id = secrets.token_hex(8)
    stored = json.dumps({"reading": reading, "note": note, "experience": bool(experience)}, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO stock_briefs (id, user_id, symbol, name, trade_date, model, facts, brief, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (brief_id, user["id"], stock.symbol, stock.name, stock.trade_date.isoformat(), model_label,
             json.dumps(stock.to_dict(), ensure_ascii=False), stored, _now()),
        )
    return _record(_load(brief_id, user))


@router.get("/briefs", summary="以前的分析")
def brief_list(limit: int = Query(20, ge=1, le=100), user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, name, trade_date, model, brief, created_at FROM stock_briefs WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?", (user["id"], limit),
        ).fetchall()
    items = []
    for row in rows:
        reading = (json.loads(row["brief"]) if row["brief"] else {}).get("reading") or {}
        items.append({"id": row["id"], "symbol": row["symbol"], "name": row["name"], "trade_date": row["trade_date"],
                      "created_at": row["created_at"], "tilt": reading.get("tilt")})
    return {"items": items}


@router.get("/briefs/{brief_id}", summary="打开一次分析")
def brief_get(brief_id: str, user: dict = Depends(get_current_user)):
    return _record(_load(brief_id, user))


@router.post("/briefs/{brief_id}/questions", summary="针对一次分析继续追问")
def brief_ask(brief_id: str, body: QuestionIn, user: dict = Depends(get_current_user)):
    record = _record(_load(brief_id, user))
    model = platform_ai.platform_model()
    if model is None:
        raise HTTPException(status_code=422, detail="平台还没有配置 AI 模型，暂时不能追问。")
    try:
        platform_ai.require_quota(user, "question")
    except platform_ai.QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    stock = StockFacts.from_dict(record["facts"])
    experience = _prior_store(user["id"]).render(None) if record["use_experience"] else ""
    messages = ask_messages(stock, record["brief"], record["questions"][-MAX_HISTORY:], body.message.strip(), experience)
    try:
        answer = platform_ai.model_client(model).chat(messages, temperature=0.3, max_tokens=600).text
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI question failed for %s: %s", brief_id, exc)
        raise HTTPException(status_code=422, detail=f"回答没有完成（{_ai_failure(exc)}），这次不计入次数。") from exc
    platform_ai.record_use(user, "question")
    questions = [*record["questions"], {"question": body.message.strip(), "answer": check_answer(answer), "at": _now()}]
    with get_conn() as conn:
        conn.execute("UPDATE stock_briefs SET questions = ? WHERE id = ? AND user_id = ?",
                     (json.dumps(questions, ensure_ascii=False), brief_id, user["id"]))
    return {"questions": questions, "usage": platform_ai.usage(user, "question")}
