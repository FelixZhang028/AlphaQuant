"""
管理员接口，挂载在 /api/v1/admin 下（仅 is_admin=1 可访问）。

- GET /users         全部用户
- GET /strategies    全部策略（跨用户）
- GET /backtests     全部回测
- GET /stats         监控快照（复用 simulator）
"""
from fastapi import APIRouter, Depends, HTTPException, status

from ..database import get_conn
from ..routes.auth import get_current_user
from ..simulator import simulator

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, name, email, created_at, is_admin FROM users ORDER BY id DESC"
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "created_at": r["created_at"],
            "is_admin": bool(r["is_admin"]),
        }
        for r in rows
    ]


@router.get("/strategies", dependencies=[Depends(require_admin)])
def list_all_strategies():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.user_id, u.email AS user_email, s.name, s.type, s.market, s.status, s.pnl, s.created_at
            FROM strategies s LEFT JOIN users u ON u.id = s.user_id
            ORDER BY s.id DESC
            """
        ).fetchall()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "user_email": r["user_email"],
            "name": r["name"],
            "type": r["type"],
            "market": r["market"],
            "status": r["status"],
            "pnl": round(r["pnl"], 2),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


@router.get("/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    return simulator.tick()
