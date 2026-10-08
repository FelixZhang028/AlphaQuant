"""
策略管理 REST 接口，挂载在 /api/v1/strategies 下（按用户隔离）。

- GET    /           列出当前用户的策略
- POST   /           新建策略
- PATCH  /{id}       更新策略状态（运行中/已暂停/已停止）
- DELETE /{id}       删除策略
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database import _now, get_conn
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/strategies", tags=["strategies"])

_STATUSES = {"运行中", "已暂停", "已停止"}


class StrategyIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    type: str = Field(..., max_length=40)
    market: str = Field(..., max_length=40)


class StatusIn(BaseModel):
    status: str


def _row_to_dict(r) -> dict:
    return {
        "id": r["id"],
        "name": r["name"],
        "type": r["type"],
        "market": r["market"],
        "status": r["status"],
        "pnl": round(r["pnl"], 2),
        "created_at": r["created_at"],
    }


@router.get("", summary="我的策略列表")
def list_strategies(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM strategies WHERE user_id = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


@router.post("", status_code=status.HTTP_201_CREATED, summary="新建策略")
def create_strategy(body: StrategyIn, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO strategies (user_id, name, type, market, status, pnl, created_at) VALUES (?,?,?,?,?,?,?)",
            (user["id"], body.name, body.type, body.market, "已暂停", 0.0, _now()),
        )
        sid = cur.lastrowid
        row = conn.execute("SELECT * FROM strategies WHERE id = ?", (sid,)).fetchone()
    return _row_to_dict(row)


@router.patch("/{sid}", summary="更新策略状态")
def update_status(sid: int, body: StatusIn, user: dict = Depends(get_current_user)):
    if body.status not in _STATUSES:
        raise HTTPException(status_code=400, detail="状态取值：运行中/已暂停/已停止")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategies WHERE id = ? AND user_id = ?", (sid, user["id"])
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="策略不存在")
        conn.execute("UPDATE strategies SET status = ? WHERE id = ?", (body.status, sid))
    return {"id": sid, "status": body.status}


@router.delete("/{sid}", status_code=status.HTTP_204_NO_CONTENT, summary="删除策略")
def delete_strategy(sid: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM strategies WHERE id = ? AND user_id = ?", (sid, user["id"])
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="策略不存在")
        conn.execute("DELETE FROM strategies WHERE id = ?", (sid,))
    return None
