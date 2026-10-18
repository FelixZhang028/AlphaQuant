"""The AI models the platform provides to every user, and how often each user may call them.

Keys live only in the server's environment; users never see or enter one. The chat model uses
``OPENROUTER_API_KEY`` (or ``FELLOWQUANT_AI_API_KEY`` for another OpenAI-compatible service). The
decision model Jev uses ``TYPESAFE_API_KEY`` (or ``JEV_API_KEY``) for TypeSafe's official API,
with ``OPENROUTER_API_KEY`` as a fallback for OpenRouter. Each kind of call
has a daily limit per user, counted in China time; administrators have none. A call is counted
only when the model answered.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from quant_platform.jev import JevClient
from quant_platform.jev.client import DEFAULT_MODEL as DEFAULT_JEV_MODEL
from quant_platform.jev.client import OPENROUTER_DECISIONS_URL
from quant_platform.jev.client import OPENROUTER_MODEL, TYPESAFE_DECISIONS_URL
from trading_agents.llm.base import OpenAICompatClient

from ..database import get_conn

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
# 种类 -> (环境变量, 默认每天次数, 页面上的说法)
LIMITS = {
    "brief": ("FELLOWQUANT_AI_DAILY_BRIEFS", 5, "AI 解读"),
    "question": ("FELLOWQUANT_AI_DAILY_QUESTIONS", 20, "追问"),
    "strategy": ("FELLOWQUANT_AI_DAILY_STRATEGIES", 10, "用一句话生成规则"),
    "review": ("FELLOWQUANT_AI_DAILY_REVIEWS", 10, "AI 评估"),
    # AI 研究员里用 Jev 判断一只股票：单独计数，不占回测 AI 评估的次数。
    "decision": ("FELLOWQUANT_AI_DAILY_DECISIONS", 10, "个股判断"),
}
CHINA = timezone(timedelta(hours=8))


@dataclass(frozen=True)
class PlatformModel:
    base_url: str
    model: str
    api_key: str

    @property
    def label(self) -> str:
        return self.model.split("/")[-1]


class QuotaExceeded(RuntimeError):
    """The user has used up today's calls of one kind."""


def platform_model() -> PlatformModel | None:
    key = os.getenv("FELLOWQUANT_AI_API_KEY", "").strip() or os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        return None
    return PlatformModel(
        base_url=os.getenv("FELLOWQUANT_AI_BASE_URL", "").strip() or DEFAULT_BASE_URL,
        model=os.getenv("FELLOWQUANT_AI_MODEL", "").strip() or DEFAULT_MODEL,
        api_key=key,
    )


def model_client(model: PlatformModel) -> OpenAICompatClient:
    return OpenAICompatClient(model=model.model, base_url=model.base_url, api_key=model.api_key)


def decision_client() -> JevClient | None:
    """Select the endpoint and model for the configured key's provider."""

    key = os.getenv("TYPESAFE_API_KEY", "").strip() or os.getenv("JEV_API_KEY", "").strip()
    url, model = TYPESAFE_DECISIONS_URL, DEFAULT_JEV_MODEL
    if not key:
        key = os.getenv("OPENROUTER_API_KEY", "").strip()
        url, model = OPENROUTER_DECISIONS_URL, OPENROUTER_MODEL
    if not key:
        return None
    return JevClient(api_key=key, base_url=os.getenv("FELLOWQUANT_JEV_URL", "").strip() or url,
                     model=os.getenv("FELLOWQUANT_JEV_MODEL", "").strip() or model)


def _today() -> str:
    return datetime.now(CHINA).date().isoformat()


def daily_limit(kind: str) -> int:
    variable, default, _ = LIMITS[kind]
    try:
        return max(0, int(os.getenv(variable, "") or default))
    except ValueError:
        return default


def usage(user: dict, kind: str) -> dict:
    """Today's limit, use and what is left; ``limit`` is None for administrators."""

    with get_conn() as conn:
        row = conn.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ? AND kind = ?",
                           (user["id"], _today(), kind)).fetchone()
    used = int(row["count"]) if row else 0
    if user.get("is_admin"):
        return {"limit": None, "used": used, "remaining": None}
    limit = daily_limit(kind)
    return {"limit": limit, "used": used, "remaining": max(0, limit - used)}


def require_quota(user: dict, kind: str) -> None:
    left = usage(user, kind)["remaining"]
    if left is not None and left <= 0:
        word = LIMITS[kind][2]
        raise QuotaExceeded(f"今天的{' ' if word[0].isascii() else ''}{word}次数已经用完（每天 {daily_limit(kind)} 次），明天再来。")


def record_use(user: dict, kind: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO ai_usage (user_id, day, kind, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(user_id, day, kind) DO UPDATE SET count = count + 1",
            (user["id"], _today(), kind),
        )


@contextmanager
def quota_call(user: dict, kind: str):
    """Reserve a daily call atomically; failed calls release the reservation.

    The transaction ends before the network request. Concurrent requests cannot all
    pass the same last remaining slot. Keep the reservation's day even across midnight.
    """
    day = _today()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ? AND kind = ?",
                           (user["id"], day, kind)).fetchone()
        if not user.get("is_admin") and (int(row["count"]) if row else 0) >= daily_limit(kind):
            word = LIMITS[kind][2]
            raise QuotaExceeded(f"今天的{' ' if word[0].isascii() else ''}{word}次数已经用完（每天 {daily_limit(kind)} 次），明天再来。")
        conn.execute(
            "INSERT INTO ai_usage (user_id, day, kind, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(user_id, day, kind) DO UPDATE SET count = count + 1",
            (user["id"], day, kind),
        )
    try:
        yield
    except BaseException:
        with get_conn() as conn:
            conn.execute("UPDATE ai_usage SET count = MAX(0, count - 1) WHERE user_id = ? AND day = ? AND kind = ?",
                         (user["id"], day, kind))
        raise
