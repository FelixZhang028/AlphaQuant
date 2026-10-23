"""The AI models the platform provides to every user, and how often each user may call them.

Keys live only in the server's environment; users never see or enter one. The chat model uses
``OPENROUTER_API_KEY`` (or ``FELLOWQUANT_AI_API_KEY`` for another OpenAI-compatible service). The
decision model Jev uses ``TYPESAFE_API_KEY`` (or ``JEV_API_KEY``) for TypeSafe's official API,
with ``OPENROUTER_API_KEY`` as a fallback for OpenRouter. Each kind of call
has free uses per user per day, counted in China time; after those each use costs points
(``points.py``). Administrators have no limit and pay no points. A call is counted (and its points
kept) only when the model answered.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from quant_platform.jev import JevClient
from quant_platform.jev.client import DEFAULT_MODEL as DEFAULT_JEV_MODEL
from quant_platform.jev.client import OPENROUTER_DECISIONS_URL
from quant_platform.jev.client import OPENROUTER_MODEL, TYPESAFE_DECISIONS_URL
from trading_agents.llm.base import OpenAICompatClient

from ..database import get_conn
from . import points

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "deepseek/deepseek-v4-pro"
# 种类 -> (环境变量, 默认每天免费次数, 页面上的说法)；免费次数用完以后每次扣积分（points.COSTS）。
LIMITS = {
    "brief": ("FELLOWQUANT_AI_DAILY_BRIEFS", 3, "AI 解读"),
    "question": ("FELLOWQUANT_AI_DAILY_QUESTIONS", 10, "追问"),
    "strategy": ("FELLOWQUANT_AI_DAILY_STRATEGIES", 5, "用一句话生成规则"),
    "review": ("FELLOWQUANT_AI_DAILY_REVIEWS", 3, "AI 评估"),
    # AI 研究员里用 Jev 判断一只股票：单独计数，不占回测 AI 评估的次数。
    "decision": ("FELLOWQUANT_AI_DAILY_DECISIONS", 3, "个股判断"),
    # AI 问答：每问一次算一次（内部要调用两次模型：先选数据，再回答）。
    "chat": ("FELLOWQUANT_AI_DAILY_CHATS", 10, "AI 问答"),
    # 条件选股：AI 一次读一整组筛出来的股票（看共同点和差别，不给股票排名）。
    "screen": ("FELLOWQUANT_AI_DAILY_SCREENS", 3, "选股解读"),
}
CHINA = timezone(timedelta(hours=8))


# 每个文本 AI 功能可以用自己的模型：种类 -> (环境变量, 页面上的说法)。和默认的文本模型用同一个接口地址、
# 同一把密钥；没单独设置就用 FELLOWQUANT_AI_MODEL。例如追问、AI 问答用快的，AI 解读、选股解读用强的。
TEXT_MODELS = {
    "brief": ("FELLOWQUANT_AI_MODEL_BRIEF", "AI 解读"),
    "screen": ("FELLOWQUANT_AI_MODEL_SCREEN", "选股解读"),
    "question": ("FELLOWQUANT_AI_MODEL_QUESTION", "追问"),
    "chat": ("FELLOWQUANT_AI_MODEL_CHAT", "AI 问答"),
    "strategy": ("FELLOWQUANT_AI_MODEL_STRATEGY", "一句话生成规则"),
}


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


def _value(config: Mapping[str, str] | None, name: str) -> str:
    """A setting from ``config`` (the admin page's unsaved values when testing) or the environment."""

    return str((os.environ if config is None else config).get(name, "") or "").strip()


def platform_model(config: Mapping[str, str] | None = None, kind: str | None = None) -> PlatformModel | None:
    """The text model for ``kind`` (one of ``TEXT_MODELS``): its own model name when one is set, else the default."""

    key = _value(config, "FELLOWQUANT_AI_API_KEY") or _value(config, "OPENROUTER_API_KEY")
    if not key:
        return None
    own = _value(config, TEXT_MODELS[kind][0]) if kind in TEXT_MODELS else ""
    return PlatformModel(
        base_url=_value(config, "FELLOWQUANT_AI_BASE_URL") or DEFAULT_BASE_URL,
        model=own or _value(config, "FELLOWQUANT_AI_MODEL") or DEFAULT_MODEL,
        api_key=key,
    )


class CountingClient:
    """The text-model client, recording each call's tokens per day (when the service reports them)."""

    def __init__(self, client: OpenAICompatClient) -> None:
        self._client = client

    def chat(self, *args, **kwargs):
        response = self._client.chat(*args, **kwargs)
        record_tokens(response.prompt_tokens, response.completion_tokens)
        return response

    def __getattr__(self, name: str):
        return getattr(self._client, name)


def extra_body(base_url: str) -> dict:
    """Extra request fields a service needs.

    DeepSeek's own API thinks before answering by default (V4 models). The thinking counts against
    ``max_tokens``, so a JSON answer can be cut off before it is written ("没有找到 JSON 对象"), and
    it costs about three times as many tokens. Our prompts ask for short, structured answers built
    from the data given, so thinking is turned off there."""

    host = (urlparse(base_url).hostname or "").lower()
    return {"thinking": {"type": "disabled"}} if host == "api.deepseek.com" else {}


def model_client(model: PlatformModel) -> CountingClient:
    return CountingClient(OpenAICompatClient(model=model.model, base_url=model.base_url, api_key=model.api_key,
                                             extra_body=extra_body(model.base_url)))


def record_tokens(prompt: int, completion: int) -> None:
    try:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO ai_tokens (day, calls, prompt, completion) VALUES (?, 1, ?, ?) ON CONFLICT(day) DO UPDATE SET "
                "calls = calls + 1, prompt = prompt + excluded.prompt, completion = completion + excluded.completion",
                (_today(), max(0, int(prompt or 0)), max(0, int(completion or 0))),
            )
    except Exception:  # noqa: BLE001 - 记不下用量也不能影响回答
        pass


def decision_client(config: Mapping[str, str] | None = None) -> JevClient | None:
    """Select the endpoint and model for the configured key's provider."""

    key = _value(config, "TYPESAFE_API_KEY") or _value(config, "JEV_API_KEY")
    url, model = TYPESAFE_DECISIONS_URL, DEFAULT_JEV_MODEL
    if not key:
        key = _value(config, "OPENROUTER_API_KEY")
        url, model = OPENROUTER_DECISIONS_URL, OPENROUTER_MODEL
    if not key:
        return None
    return JevClient(api_key=key, base_url=_value(config, "FELLOWQUANT_JEV_URL") or url,
                     model=_value(config, "FELLOWQUANT_JEV_MODEL") or model)


def _today() -> str:
    return datetime.now(CHINA).date().isoformat()


# 全站每天最多调用 AI 的次数（所有用户、所有种类加起来；管理员的调用计入但不受限制）。
# 每个账户都有自己的次数，批量注册的账户加起来也不能超过这个总数。0 表示不限。
TOTAL_VARIABLE, TOTAL_DEFAULT = "FELLOWQUANT_AI_DAILY_TOTAL", 500


def daily_total_limit() -> int:
    try:
        return max(0, int(os.getenv(TOTAL_VARIABLE, "") or TOTAL_DEFAULT))
    except ValueError:
        return TOTAL_DEFAULT


def daily_limit(kind: str) -> int:
    variable, default, _ = LIMITS[kind]
    try:
        return max(0, int(os.getenv(variable, "") or default))
    except ValueError:
        return default


def usage(user: dict, kind: str) -> dict:
    """Today's free uses (limit, used, left), the points one more use costs after that, and the balance.
    ``limit`` and ``points`` are None for administrators (no limit, no points)."""

    with get_conn() as conn:
        row = conn.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ? AND kind = ?",
                           (user["id"], _today(), kind)).fetchone()
        have = None
        if not user.get("is_admin"):
            points.ensure_signup(conn, user["id"])      # 有积分以前注册的账户，第一次看到时补上注册赠送
            have = points.balance(conn, user["id"])
    used = int(row["count"]) if row else 0
    if user.get("is_admin"):
        return {"limit": None, "used": used, "remaining": None, "cost": 0, "points": None}
    limit = daily_limit(kind)
    return {"limit": limit, "used": used, "remaining": max(0, limit - used), "cost": points.cost(kind), "points": have}


def _short_text(kind: str, need: int, have: int) -> str:
    word = LIMITS[kind][2]
    return (f"今天的免费{word}次数已经用完（每天 {daily_limit(kind)} 次）。再用一次要 {need} 积分，"
            f"你现在有 {have} 积分；可以在“积分”页面用兑换码兑换积分。")


def usage_history(days: int = 30) -> dict:
    """The last ``days`` days (China time), oldest first: calls per kind and tokens per day, and the
    heaviest users over the period. Only what was recorded: tokens are there when the service reports them."""

    end = datetime.now(CHINA).date()
    start = end - timedelta(days=days - 1)
    span = [(start + timedelta(days=i)).isoformat() for i in range(days)]
    with get_conn() as conn:
        counts = conn.execute("SELECT day, kind, SUM(count) AS n FROM ai_usage WHERE day >= ? GROUP BY day, kind",
                              (start.isoformat(),)).fetchall()
        tokens = {row["day"]: row for row in conn.execute("SELECT * FROM ai_tokens WHERE day >= ?", (start.isoformat(),)).fetchall()}
        top = conn.execute(
            "SELECT u.id, u.name, u.email, u.is_admin, SUM(a.count) AS n FROM ai_usage a JOIN users u ON u.id = a.user_id "
            "WHERE a.day >= ? GROUP BY u.id ORDER BY n DESC LIMIT 10", (start.isoformat(),)).fetchall()
    by_day = {day: {kind: 0 for kind in LIMITS} for day in span}
    for row in counts:
        if row["day"] in by_day and row["kind"] in LIMITS:
            by_day[row["day"]][row["kind"]] = int(row["n"] or 0)
    rows = []
    for day in span:
        token = tokens.get(day)
        rows.append({"day": day, "kinds": by_day[day], "total": sum(by_day[day].values()),
                     "tokens": (int(token["prompt"]) + int(token["completion"])) if token else 0,
                     "model_calls": int(token["calls"]) if token else 0})
    return {"days": rows, "labels": {kind: word for kind, (_, _, word) in LIMITS.items()},
            "top_users": [{"id": row["id"], "name": row["name"], "email": row["email"], "is_admin": bool(row["is_admin"]),
                           "count": int(row["n"] or 0)} for row in top],
            "total": sum(row["total"] for row in rows), "tokens": sum(row["tokens"] for row in rows)}


@contextmanager
def quota_call(user: dict, kind: str):
    """Reserve one use atomically: a free use of the day if any is left, otherwise the points it costs.
    A failed call gives back the use (and the points).

    The transaction ends before the network request. Concurrent requests cannot all
    pass the same last remaining slot or spend the same points. Keep the reservation's day even across midnight.
    """
    day = _today()
    spent = None
    if not user.get("is_admin"):
        with get_conn() as conn:
            points.ensure_signup(conn, user["id"])      # 单独提交：后面被拒绝时也不会把注册赠送一起撤销
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT count FROM ai_usage WHERE user_id = ? AND day = ? AND kind = ?",
                           (user["id"], day, kind)).fetchone()
        if not user.get("is_admin"):
            total = conn.execute("SELECT count FROM ai_usage_total WHERE day = ?", (day,)).fetchone()
            if daily_total_limit() and (int(total["count"]) if total else 0) >= daily_total_limit():
                raise QuotaExceeded("平台今天的 AI 次数已经用完，明天再来。")
            cap = points.daily_cap()
            mine = conn.execute("SELECT COALESCE(SUM(count), 0) AS n FROM ai_usage WHERE user_id = ? AND day = ?",
                                (user["id"], day)).fetchone()
            if cap and int(mine["n"]) >= cap:
                raise QuotaExceeded(f"今天已经用了 {int(mine['n'])} 次 AI，达到每人每天的上限（{cap} 次），明天再来。")
            if (int(row["count"]) if row else 0) >= daily_limit(kind):
                need = points.cost(kind)
                try:
                    spent = points.spend(conn, user["id"], need, kind)
                except points.PointsShort as short:
                    raise QuotaExceeded(_short_text(kind, need, int(short.args[0]))) from None
        conn.execute(
            "INSERT INTO ai_usage (user_id, day, kind, count) VALUES (?, ?, ?, 1) "
            "ON CONFLICT(user_id, day, kind) DO UPDATE SET count = count + 1",
            (user["id"], day, kind),
        )
        conn.execute("INSERT INTO ai_usage_total (day, count) VALUES (?, 1) ON CONFLICT(day) DO UPDATE SET count = count + 1", (day,))
    try:
        yield
    except BaseException:
        with get_conn() as conn:
            conn.execute("UPDATE ai_usage SET count = MAX(0, count - 1) WHERE user_id = ? AND day = ? AND kind = ?",
                         (user["id"], day, kind))
            conn.execute("UPDATE ai_usage_total SET count = MAX(0, count - 1) WHERE day = ?", (day,))
        if spent is not None:
            points.refund(spent)
        raise
