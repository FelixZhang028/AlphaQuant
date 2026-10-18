"""AI 研究员路由：用本地数据读懂一只股票。

分两步：先从本地数据整理出这只股票当天的数据（价格走势、成交、全市场比较、估值、财报、
行业、指数、分红），不需要 AI，也不限次数；页面马上显示。平台配置了 AI 模型时，再让模型只
根据保存的这些数据写出倾向和要点，检查不通过的要点会被去掉。每次结果都保存，可以打开、
继续追问，并对照之后实际的涨跌。

研究经验（先验知识）按用户隔离，存放于 data/runtime/agent_lab/user_{id}/。
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import threading
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
from quant_platform.ai_research.decisions import tilt_odds
from quant_platform.ai_research.stock_report import REPORT_VERSION, stock_report
from quant_platform.ai_research.facts import StockFacts, stock_facts
from quant_platform.ai_research.outcome import later_moves

from ..database import get_conn
from ..quant import platform_ai
from ..quant.compute import computing
from ..quant.runtime import BACKEND_ROOT, market_repository, security_names
from ..quant.symbols import to_bare, to_canonical
from ..routes.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/agent-lab", tags=["agent-lab"])

_AGENT_ROOT = BACKEND_ROOT / "data" / "runtime" / "agent_lab"
# 追问时带上最近几轮对话，太早的不再发给模型。
MAX_HISTORY = 6
TEXT_MODEL_NOTE = "平台还没有配置文本模型，暂不提供文字解读和追问。"
LEGACY_MODEL_NOTE = "平台还没有配置 AI 模型，这次只显示数据。"
# 正在解读的分析：同一次分析不会同时问两次模型（也就不会重复计数）。
_READING: set[str] = set()
_READING_LOCK = threading.Lock()


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
    decision = platform_ai.decision_client()
    bounds = market_repository().daily_bar_bounds()
    return {
        "ai": {"available": model is not None, "model": model.label if model else None},
        "decision": {"available": decision is not None, "model": decision.model if decision else None},
        "usage": {kind: platform_ai.usage(user, kind) for kind in ("brief", "question", "decision")},
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
        "odds": stored.get("odds") or (stored.get("reading") or {}).get("odds"),
        "ai_note": TEXT_MODEL_NOTE if stored.get("note") == LEGACY_MODEL_NOTE else stored.get("note", ""),
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


def _store_reading(brief_id: str, user: dict, reading: dict[str, Any] | None, note: str, experience: bool, model: str) -> None:
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT brief FROM stock_briefs WHERE id = ? AND user_id = ?", (brief_id, user["id"])).fetchone()
        stored = json.loads(row["brief"]) if row and row["brief"] else {}
        stored.update(reading=reading, note=note, experience=experience)
        conn.execute("UPDATE stock_briefs SET brief = ?, model = ? WHERE id = ? AND user_id = ?",
                     (json.dumps(stored, ensure_ascii=False), model, brief_id, user["id"]))


def _with_later(record: dict[str, Any]) -> dict[str, Any]:
    day = date.fromisoformat(record["trade_date"])
    moves = later_moves(market_repository(), [(record["symbol"], day)])
    return {**record, "later": moves.get((record["symbol"], day))}


def _tilt_odds(stock: StockFacts) -> dict[str, Any] | None:
    """决策模型 Jev 对同一张数据表给出的倾向概率；没有配置或失败时不显示。"""
    client = platform_ai.decision_client()
    if client is None:
        return None
    try:
        return tilt_odds(client, stock)
    except Exception as exc:  # noqa: BLE001 - 第二个模型失败不影响解读
        logger.warning("Jev tilt failed for %s: %s", stock.symbol, exc)
        return None


@router.post("/briefs", status_code=status.HTTP_201_CREATED, summary="分析一只股票，第一步：整理本地数据（不用 AI）")
def brief_create(body: BriefIn, user: dict = Depends(get_current_user)):
    symbol = to_canonical(body.symbol.strip())
    try:
        day = date.fromisoformat(body.trade_date) if body.trade_date else None
    except ValueError:
        raise HTTPException(status_code=422, detail="分析日期格式无效") from None
    names = security_names()
    name = names.get(symbol) or names.get(to_bare(symbol)) or symbol
    try:
        with computing(user):
            stock = stock_facts(market_repository(), symbol, day, name=name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc)) from exc

    note = "" if platform_ai.platform_model() else TEXT_MODEL_NOTE
    brief_id = secrets.token_hex(8)
    stored = json.dumps({"reading": None, "note": note, "experience": body.use_experience}, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO stock_briefs (id, user_id, symbol, name, trade_date, model, facts, brief, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (brief_id, user["id"], stock.symbol, stock.name, stock.trade_date.isoformat(), "",
             json.dumps(stock.to_dict(), ensure_ascii=False), stored, _now()),
        )
    return _with_later(_record(_load(brief_id, user)))


@router.post("/briefs/{brief_id}/reading", summary="分析一只股票，第二步：AI 根据保存的数据写解读")
def brief_reading(brief_id: str, user: dict = Depends(get_current_user)):
    record = _record(_load(brief_id, user))
    if record["brief"] is not None:
        return _with_later(record)  # 已经解读过，不再调用、不再计数
    model = platform_ai.platform_model()
    if model is None:
        _store_reading(brief_id, user, None, TEXT_MODEL_NOTE, record["use_experience"], "")
        return _with_later(_record(_load(brief_id, user)))
    with _READING_LOCK:
        if brief_id in _READING:
            raise HTTPException(status_code=409, detail="这次分析正在解读，请稍候")
        _READING.add(brief_id)
    try:
        reading, label, note = None, "", ""
        try:
            experience = _prior_store(user["id"]).render(None) if record["use_experience"] else ""
            stock = StockFacts.from_dict(record["facts"])
            with platform_ai.quota_call(user, "brief"):
                reading = _read_brief(model, stock, experience)
            label = model.label
            reading["odds"] = record["odds"] or _tilt_odds(stock)
        except platform_ai.QuotaExceeded as exc:
            note = f"{exc}下面的数据不受次数限制。"
        except Exception as exc:  # noqa: BLE001 - 模型失败时仍然给出数据
            logger.warning("AI brief failed for %s: %s", record["symbol"], exc)
            note = f"AI 解读没有完成（{_ai_failure(exc)}），这次不计入次数。下面的数据仍然可以参考。"
        _store_reading(brief_id, user, reading, note, record["use_experience"], label)
    finally:
        with _READING_LOCK:
            _READING.discard(brief_id)
    return _with_later(_record(_load(brief_id, user)))


@router.post("/briefs/{brief_id}/decision", summary="用 Jev 判断已保存的数据，不需要文本模型")
def brief_decision(brief_id: str, upgrade: bool = Query(False), user: dict = Depends(get_current_user)):
    record = _record(_load(brief_id, user))
    if record["odds"] is not None and (not upgrade or record["odds"].get("report_version", 1) >= REPORT_VERSION):
        return _with_later(record)
    client = platform_ai.decision_client()
    if client is None:
        raise HTTPException(status_code=422, detail="平台还没有配置决策模型，暂时不能使用。")
    try:
        with computing(user):
            # Re-read under the per-user computation guard to prevent duplicate upgrades.
            record = _record(_load(brief_id, user))
            if record["odds"] is not None and (not upgrade or record["odds"].get("report_version", 1) >= REPORT_VERSION):
                return _with_later(record)
            return _save_stock_report(brief_id, user, record, client)
    except platform_ai.QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"决策模型调用失败：{_ai_failure(exc)}") from None


def _save_stock_report(brief_id: str, user: dict, record: dict, client):
    with platform_ai.quota_call(user, "decision"):
        odds = stock_report(client, StockFacts.from_dict(record["facts"]))
        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT brief FROM stock_briefs WHERE id = ? AND user_id = ?", (brief_id, user["id"])).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="没有找到这次分析")
            stored = json.loads(row["brief"]) if row["brief"] else {}
            stored["odds"] = odds
            conn.execute("UPDATE stock_briefs SET brief = ? WHERE id = ? AND user_id = ?",
                         (json.dumps(stored, ensure_ascii=False), brief_id, user["id"]))
    return _with_later(_record(_load(brief_id, user)))


@router.get("/briefs", summary="以前的分析，以及之后实际涨跌")
def brief_list(limit: int = Query(20, ge=1, le=100), user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, symbol, name, trade_date, model, brief, created_at FROM stock_briefs WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT ?", (user["id"], limit),
        ).fetchall()
    moves = later_moves(market_repository(), [(row["symbol"], date.fromisoformat(row["trade_date"])) for row in rows])
    items = []
    for row in rows:
        stored = json.loads(row["brief"]) if row["brief"] else {}
        reading = stored.get("reading") or {}
        odds = stored.get("odds") or reading.get("odds") or {}
        items.append({"id": row["id"], "symbol": row["symbol"], "name": row["name"], "trade_date": row["trade_date"],
                      "created_at": row["created_at"], "tilt": reading.get("tilt") or odds.get("choice"),
                      "later": moves.get((row["symbol"], date.fromisoformat(row["trade_date"])))})
    return {"items": items}


@router.get("/briefs/{brief_id}", summary="打开一次分析")
def brief_get(brief_id: str, user: dict = Depends(get_current_user)):
    return _with_later(_record(_load(brief_id, user)))


@router.delete("/briefs/{brief_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除一次分析")
def brief_delete(brief_id: str, user: dict = Depends(get_current_user)):
    _load(brief_id, user)
    with get_conn() as conn:
        conn.execute("DELETE FROM stock_briefs WHERE id = ? AND user_id = ?", (brief_id, user["id"]))


@router.post("/briefs/{brief_id}/questions", summary="针对一次分析继续追问")
def brief_ask(brief_id: str, body: QuestionIn, user: dict = Depends(get_current_user)):
    record = _record(_load(brief_id, user))
    model = platform_ai.platform_model()
    if model is None:
        raise HTTPException(status_code=422, detail="平台还没有配置文本模型，暂时不能追问。")
    stock = StockFacts.from_dict(record["facts"])
    experience = _prior_store(user["id"]).render(None) if record["use_experience"] else ""
    messages = ask_messages(stock, record["brief"], record["questions"][-MAX_HISTORY:], body.message.strip(), experience)
    try:
        with platform_ai.quota_call(user, "question"):
            answer = platform_ai.model_client(model).chat(messages, temperature=0.3, max_tokens=600).text
    except platform_ai.QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI question failed for %s: %s", brief_id, exc)
        raise HTTPException(status_code=422, detail=f"回答没有完成（{_ai_failure(exc)}），这次不计入次数。") from exc
    questions = [*record["questions"], {"question": body.message.strip(), "answer": check_answer(answer), "at": _now()}]
    with get_conn() as conn:
        conn.execute("UPDATE stock_briefs SET questions = ? WHERE id = ? AND user_id = ?",
                     (json.dumps(questions, ensure_ascii=False), brief_id, user["id"]))
    return {"questions": questions, "usage": platform_ai.usage(user, "question")}
