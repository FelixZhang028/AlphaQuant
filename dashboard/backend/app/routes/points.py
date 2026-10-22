"""
积分接口，挂载在 /api/v1/points 下。

- GET  /         我的积分：余额、每一批和到期时间、最近的明细、每种 AI 功能的免费次数和价格
- POST /redeem   用兑换码兑换积分
- POST /checkin  每日打卡（北京时间每天一次，连续打卡送得越来越多）
- POST /makeup   用一张补签卡补最近漏掉的一天
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..quant import points, rate_limit
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/points", tags=["points"])

REDEEM_LIMIT = (20, 60 * 60)          # 每人每小时最多试 20 次兑换码，防止猜码


class RedeemIn(BaseModel):
    code: str = Field(..., min_length=1, max_length=60)


@router.get("", summary="我的积分")
def my_points(user: dict = Depends(get_current_user)):
    return points.summary(user)


@router.post("/redeem", summary="用兑换码兑换积分")
def redeem_code(body: RedeemIn, user: dict = Depends(get_current_user)):
    rate_limit.check(f"redeem:{user['id']}", *REDEEM_LIMIT, "兑换尝试太频繁，请一小时后再试")
    result = points.redeem(user["id"], body.code)
    return {**result, "summary": points.summary(user)}


@router.post("/checkin", summary="每日打卡")
def daily_checkin(user: dict = Depends(get_current_user)):
    result = points.checkin(user)
    return {**result, "summary": points.summary(user)}


@router.post("/makeup", summary="用补签卡补最近漏掉的一天")
def use_makeup_card(user: dict = Depends(get_current_user)):
    result = points.makeup(user)
    return {**result, "summary": points.summary(user)}
