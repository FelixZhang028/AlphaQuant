"""
个人设置接口，挂载在 /api/v1/settings 下。

- GET /preferences   研究默认值（没保存过的项用平台默认值）
- PUT /preferences   保存研究默认值：回测的初始资金、最多持仓、调仓频率、回测区间，AI 研究员是否参考研究经验
- GET /usage         今天各类 AI 的次数和剩余
- GET /export        导出我的全部数据（一个 JSON 文件）；隐私政策里承诺的“复制个人信息”
"""
import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from ..database import get_conn
from ..quant import platform_ai, rate_limit
from ..quant.accounts import export_account
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    initial_capital: float = Field(1_000_000, ge=10_000, le=100_000_000, allow_inf_nan=False, description="回测初始资金")
    max_positions: int = Field(10, ge=1, le=50, description="最多持有几只")
    rebalance: Literal["daily", "weekly", "monthly"] = Field("weekly", description="调仓频率")
    period_years: int = Field(1, ge=1, le=10, description="默认回测最近几年")
    use_experience: bool = Field(True, description="AI 研究员默认参考我的研究经验")


DEFAULTS = Preferences().model_dump()


def load_preferences(user_id: int) -> dict:
    with get_conn() as conn:
        row = conn.execute("SELECT data FROM user_preferences WHERE user_id = ?", (user_id,)).fetchone()
    saved = {}
    if row:
        try:
            saved = json.loads(row["data"]) or {}
        except ValueError:
            saved = {}
    merged = {**DEFAULTS, **{key: value for key, value in saved.items() if key in DEFAULTS}}
    try:
        return Preferences(**merged).model_dump()
    except ValueError:
        return dict(DEFAULTS)            # 保存的内容不合规（例如以后改了范围）时用默认值


@router.get("/preferences", summary="研究默认值")
def get_preferences(user: dict = Depends(get_current_user)):
    return {"preferences": load_preferences(user["id"]), "defaults": DEFAULTS}


@router.put("/preferences", summary="保存研究默认值")
def save_preferences(body: Preferences, user: dict = Depends(get_current_user)):
    data = body.model_dump()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_preferences (user_id, data, updated_at) VALUES (?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (user["id"], json.dumps(data, ensure_ascii=False), datetime.now(timezone.utc).isoformat()),
        )
    return {"preferences": data, "defaults": DEFAULTS}


@router.get("/usage", summary="今天各类 AI 的次数")
def today_usage(user: dict = Depends(get_current_user)):
    items = [{"kind": kind, "label": word, **platform_ai.usage(user, kind)}
             for kind, (_variable, _default, word) in platform_ai.LIMITS.items()]
    return {"day": platform_ai._today(), "items": items, "unlimited": bool(user.get("is_admin"))}


@router.get("/export", summary="导出我的全部数据")
def export_my_data(user: dict = Depends(get_current_user)):
    rate_limit.check(f"export:{user['id']}", 10, 60 * 60, "导出太频繁")
    data = export_account(user["id"])
    name = f"prismind-{datetime.now(platform_ai.CHINA):%Y%m%d}.json"
    return JSONResponse(content=data, headers={"Content-Disposition": f'attachment; filename="{name}"'})
