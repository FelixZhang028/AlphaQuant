"""
管理员接口，挂载在 /api/v1/admin 下（仅 is_admin=1 可访问）。

- GET /users   全部用户（含最后访问时间）
- GET /stats   平台的真实数字：用户、研究、AI 用量、邀请码、注册方式、备份
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_conn
from ..quant import backup, platform_ai, registration
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, email, created_at, is_admin, last_seen_at FROM users ORDER BY id DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "created_at": r["created_at"],
            "last_seen_at": r["last_seen_at"],
            "is_admin": bool(r["is_admin"]),
        }
        for r in rows
    ]


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
        used = {r["code"]: int(r["used"]) for r in conn.execute("SELECT code, used FROM invite_uses")}
    words = {kind: word for kind, (_variable, _default, word) in platform_ai.LIMITS.items()}
    ai = {
        "day": today,
        "used": int(total_row["count"]) if total_row else 0,     # 含管理员的调用
        "limit": platform_ai.daily_total_limit(),
        "by_kind": [{"kind": kind, "label": words.get(kind, kind), "count": count} for kind, count in sorted(by_kind.items())],
    }
    invites = [{"code": code, "limit": limit, "used": used.get(code, 0)} for code, limit in registration.invite_codes().items()]
    return {
        "users": users,
        "research": research,
        "ai": ai,
        "registration": {"mode": registration.mode(), "invites": invites},
        "backup": _latest_backup(),
    }
