"""
管理员接口，挂载在 /api/v1/admin 下（仅 is_admin=1 可访问）。

- GET  /users                 全部用户：最后访问、今天和累计的 AI 次数、回测数、是否停用
- POST /users/{id}/active     停用或恢复一个账户（管理员账户不能停用）
- GET  /stats                 平台的真实数字：用户、研究、AI 用量、邀请码、注册方式、备份
- GET  /registration          注册方式和全部邀请码
- PUT  /registration          改注册方式：open 开放 / invite 凭邀请码 / closed 暂停
- POST /invites               生成邀请码（可以指定码、次数和备注）
- POST /invites/{code}/active 停用或恢复页面生成的邀请码
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database import get_conn
from ..quant import backup, platform_ai, registration
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


class ActiveIn(BaseModel):
    active: bool


class ModeIn(BaseModel):
    mode: str


class InviteIn(BaseModel):
    code: str = Field("", max_length=32, description="留空自动生成")
    max_uses: int | None = Field(None, ge=1, le=100000, description="最多注册几个人，留空不限")
    note: str = Field("", max_length=60, description="备注，例如发给谁")


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.name, u.email, u.created_at, u.is_admin, u.is_active, u.last_seen_at,
                   (SELECT COALESCE(SUM(a.count), 0) FROM ai_usage a WHERE a.user_id = u.id AND a.day = ?) AS ai_today,
                   (SELECT COALESCE(SUM(a.count), 0) FROM ai_usage a WHERE a.user_id = u.id) AS ai_total,
                   (SELECT COUNT(*) FROM backtests b WHERE b.user_id = u.id) AS backtests
            FROM users u ORDER BY u.id DESC
            """,
            (platform_ai._today(),),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "created_at": r["created_at"],
            "last_seen_at": r["last_seen_at"],
            "is_admin": bool(r["is_admin"]),
            "is_active": bool(r["is_active"]),
            "ai_today": int(r["ai_today"]),
            "ai_total": int(r["ai_total"]),
            "backtests": int(r["backtests"]),
        }
        for r in rows
    ]


@router.post("/users/{uid}/active", dependencies=[Depends(require_admin)])
def set_user_active(uid: int, body: ActiveIn):
    """停用：不能再登录，已经登录的设备立即失效；恢复：可以重新登录。账户里的数据都不动。"""

    with get_conn() as conn:
        row = conn.execute("SELECT is_admin FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="没有这个用户")
        if row["is_admin"]:
            raise HTTPException(status_code=403, detail="管理员账户不能停用")
        conn.execute("UPDATE users SET is_active = ?, token_version = token_version + ? WHERE id = ?",
                     (1 if body.active else 0, 0 if body.active else 1, uid))
    return {"id": uid, "is_active": body.active}


@router.get("/registration", dependencies=[Depends(require_admin)])
def registration_settings():
    return {"mode": registration.mode(), "locked": registration.env_locked(), "invites": registration.all_codes()}


@router.put("/registration", dependencies=[Depends(require_admin)])
def change_registration(body: ModeIn):
    registration.set_mode(body.mode)
    return registration_settings()


@router.post("/invites", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_invite(body: InviteIn):
    code = registration.create_code(body.code, body.max_uses, body.note)
    return {"code": code, **registration_settings()}


@router.post("/invites/{code}/active", dependencies=[Depends(require_admin)])
def set_invite_active(code: str, body: ActiveIn):
    registration.set_code_active(code, body.active)
    return registration_settings()


def _china_day_start() -> str:
    """今天（北京时间）0 点对应的 UTC 时间；数据库里的时间都是 UTC 的 ISO 文本，可以直接比较。"""

    start = datetime.now(platform_ai.CHINA).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat()


def _count(conn, sql: str, *args) -> int:
    return int(conn.execute(sql, args).fetchone()[0] or 0)


def _latest_backup() -> dict:
    root = backup.backup_root()
    folders = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []
    return {"enabled": backup.enabled(), "latest": folders[-1] if folders else None, "count": len(folders), "keep": backup.keep()}


@router.get("/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    today, since = platform_ai._today(), _china_day_start()
    with get_conn() as conn:
        users = {
            "total": _count(conn, "SELECT COUNT(*) FROM users"),
            "new_today": _count(conn, "SELECT COUNT(*) FROM users WHERE created_at >= ?", since),
            "active_today": _count(conn, "SELECT COUNT(*) FROM users WHERE last_seen_at >= ?", since),
        }
        research = {
            "backtests": _count(conn, "SELECT COUNT(*) FROM backtests"),
            "backtests_today": _count(conn, "SELECT COUNT(*) FROM backtests WHERE created_at >= ?", since),
            "strategies": _count(conn, "SELECT COUNT(*) FROM strategy_packages"),
            "briefs": _count(conn, "SELECT COUNT(*) FROM stock_briefs"),
            "briefs_today": _count(conn, "SELECT COUNT(*) FROM stock_briefs WHERE created_at >= ?", since),
        }
        by_kind = {r["kind"]: int(r["total"]) for r in conn.execute(
            "SELECT kind, SUM(count) AS total FROM ai_usage WHERE day = ? GROUP BY kind", (today,))}
        total_row = conn.execute("SELECT count FROM ai_usage_total WHERE day = ?", (today,)).fetchone()
        disabled = _count(conn, "SELECT COUNT(*) FROM users WHERE is_active = 0")
    words = {kind: word for kind, (_variable, _default, word) in platform_ai.LIMITS.items()}
    ai = {
        "day": today,
        "used": int(total_row["count"]) if total_row else 0,     # 含管理员的调用
        "limit": platform_ai.daily_total_limit(),
        "by_kind": [{"kind": kind, "label": words.get(kind, kind), "count": count} for kind, count in sorted(by_kind.items())],
    }
    invites = [item for item in registration.all_codes() if item["active"]]
    users["disabled"] = disabled
    return {
        "users": users,
        "research": research,
        "ai": ai,
        "registration": {"mode": registration.mode(), "invites": invites},
        "backup": _latest_backup(),
    }
