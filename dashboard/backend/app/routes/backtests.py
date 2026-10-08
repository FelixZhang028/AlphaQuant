"""
回测任务接口，挂载在 /api/v1/backtests 下（按用户隔离）。

- POST /   提交回测任务（真实引擎：quant_platform BacktestService）
- GET  /   列出当前用户的历史回测

绩效指标（由回测引擎计算）：
- equity     资金曲线序列
- total_return 总收益率(%)
- max_drawdown  最大回撤(%)
- sharpe       夏普比率（年化，基于日收益）
- win_rate     胜率(%)
"""
import json
from dataclasses import replace as dc_replace
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database import _now, get_conn
from ..quant.result_adapter import backtest_run_to_result
from ..quant.runtime import (
    build_backtest_service,
    local_data_bounds,
    security_names,
    user_risk_limits,
)
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


class BacktestIn(BaseModel):
    strategy: str = Field(..., max_length=60)
    market: str = Field(..., max_length=40)
    from_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    to_date: str = Field(..., description="结束日期 YYYY-MM-DD")


def _resolve_plugin(service, strategy_name: str) -> str:
    """按显示名或插件名匹配策略；匹配不到时回退到配置默认策略。"""

    for metadata in service.available_strategies():
        if strategy_name in (metadata.display_name, metadata.plugin_name):
            return metadata.plugin_name
    return service.default_request().strategy_plugin


# 引擎英文报错 -> 中文提示（避免把 "No daily bars available for backtest" 直接抛给用户）
_ENGINE_ERRORS = {
    "No daily bars available for backtest": "本地没有所选区间的日线数据，请先在数据管理中下载行情。",
    "No trading calendar data in requested range": "所选区间没有交易日历数据，请先在数据管理中下载数据。",
}


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    for english, chinese in _ENGINE_ERRORS.items():
        if english in text:
            return chinese
    return f"回测失败：{text}"


@router.post("", status_code=status.HTTP_201_CREATED, summary="提交回测任务")
def submit_backtest(body: BacktestIn, user: dict = Depends(get_current_user)):
    if body.from_date >= body.to_date:
        raise HTTPException(status_code=400, detail="开始日期需早于结束日期")
    bounds = local_data_bounds()
    if bounds is None:
        raise HTTPException(status_code=409, detail="本地暂无行情数据，请先在数据管理中下载。")
    local_start, local_end = bounds
    # 请求区间收敛到本地数据范围：引擎只会在有数据的区间内执行，
    # 同时把实际执行区间入库，避免 UI 展示一个未被评估的空区间。
    start = max(body.from_date, local_start.isoformat())
    end = min(body.to_date, local_end.isoformat())
    if start >= end:
        raise HTTPException(
            status_code=422,
            detail=f"所选区间与本地数据（{local_start} ~ {local_end}）无交集。",
        )

    service = build_backtest_service(user)
    plugin = _resolve_plugin(service, body.strategy.strip())
    request = dc_replace(
        service.default_request(),
        strategy_plugin=plugin,
        strategy_id=f"{plugin}_{uuid4().hex[:8]}",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        risk_limits=user_risk_limits(user["id"]),
    )
    try:
        run = service.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_friendly_error(exc))
    except Exception as exc:  # noqa: BLE001 - 引擎内部错误统一转 422
        raise HTTPException(status_code=422, detail=_friendly_error(exc))

    result = backtest_run_to_result(run, names=security_names())
    payload = json.dumps(result, ensure_ascii=False)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO backtests (user_id, strategy, market, from_date, to_date, status, result, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], body.strategy, body.market, start, end, "完成", payload, _now()),
        )
        bid = cur.lastrowid
    return {"id": bid, "status": "完成", "result": result, "created_at": _now()}


@router.get("/{bid}", summary="单次回测详情")
def get_backtest(bid: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backtests WHERE id = ? AND user_id = ?", (bid, user["id"])
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回测不存在")
    result = json.loads(row["result"]) if row["result"] else {}
    return {
        "id": row["id"],
        "strategy": row["strategy"],
        "market": row["market"],
        "from_date": row["from_date"],
        "to_date": row["to_date"],
        "status": row["status"],
        "created_at": row["created_at"],
        "result": result,
        "trades": result.get("trades") or [],
        "positions": result.get("positions") or [],
    }


@router.get("", summary="我的回测历史")
def list_backtests(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, strategy, market, from_date, to_date, status, result, created_at FROM backtests WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    out = []
    for r in rows:
        out.append(
            {
                "id": r["id"],
                "strategy": r["strategy"],
                "market": r["market"],
                "from_date": r["from_date"],
                "to_date": r["to_date"],
                "status": r["status"],
                "result": json.loads(r["result"]) if r["result"] else None,
                "created_at": r["created_at"],
            }
        )
    return out
