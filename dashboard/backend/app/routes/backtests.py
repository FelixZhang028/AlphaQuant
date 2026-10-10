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
from dataclasses import asdict, replace as dc_replace
from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Literal

from ..database import _now, get_conn
from ..quant.result_adapter import backtest_run_to_result
from ..quant.run_evidence import with_run_evidence
from ..quant.runtime import (
    build_backtest_service,
    local_data_bounds,
    security_names,
    user_risk_limits,
)
from ..routes.auth import get_current_user

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


class BacktestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    strategy: str = Field(..., max_length=160)
    market: str = Field(..., max_length=40)
    from_date: str = Field(..., description="开始日期 YYYY-MM-DD")
    to_date: str = Field(..., description="结束日期 YYYY-MM-DD")
    initial_capital: float = Field(1_000_000, gt=0, allow_inf_nan=False)
    max_positions: int = Field(10, ge=1, le=500)
    rebalance: Literal["daily", "weekly", "monthly"] = "weekly"
    strategy_parameters: dict[str, Any] = Field(default_factory=dict)


def _resolve_plugin(service, strategy_name: str) -> str:
    """Unknown strategies must never silently execute another strategy."""

    for metadata in service.available_strategies():
        if strategy_name in (metadata.display_name, metadata.plugin_name):
            return metadata.plugin_name
    raise HTTPException(status_code=422, detail="策略不存在或加载失败，请选择已注册策略。")


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
    if body.market != "当前股票池":
        raise HTTPException(status_code=422, detail="目前仅支持当前 A 股股票池；指数成分及海外市场尚未接入。")
    try:
        date.fromisoformat(body.from_date)
        date.fromisoformat(body.to_date)
    except ValueError:
        raise HTTPException(status_code=422, detail="日期格式需为 YYYY-MM-DD")
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

    if body.strategy.startswith("package:"):
        from .workspace import PackageBacktestIn, backtest_package
        if body.max_positions > 50:
            raise HTTPException(status_code=422, detail="规则策略最多支持持有 50 只股票。")
        if body.strategy_parameters:
            raise HTTPException(status_code=422, detail="规则策略请在创建页修改指标规则。")
        return backtest_package(body.strategy.removeprefix("package:"), PackageBacktestIn(
            from_date=start, to_date=end, initial_cash=body.initial_capital,
            top_n=body.max_positions, rebalance=body.rebalance), user)

    service = build_backtest_service(user)
    reference = body.strategy.strip()
    if reference.startswith("user:"):
        plugin = getattr(service, "user_strategy_plugins", {}).get(reference.removeprefix("user:"))
        if not plugin:
            raise HTTPException(status_code=422, detail="该 Python 策略未能加载，请检查代码和注册标识；未执行其他策略。")
    else:
        plugin = _resolve_plugin(service, reference)
    defaults = service.default_request()
    metadata = next(m for m in service.available_strategies() if m.plugin_name == plugin)
    parameters = defaults.strategy_parameters if plugin == defaults.strategy_plugin else metadata.defaults()
    if body.strategy_parameters:
        try:
            parameters = metadata.validate_parameters({**parameters, **body.strategy_parameters})
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"策略参数无效：{exc}")
    effective_risk = dc_replace(user_risk_limits(user["id"]), max_positions=body.max_positions)
    request = dc_replace(
        defaults,
        strategy_plugin=plugin,
        strategy_id=f"{plugin}_{uuid4().hex[:8]}",
        start_date=date.fromisoformat(start),
        end_date=date.fromisoformat(end),
        initial_cash=body.initial_capital,
        top_n=body.max_positions,
        rebalance=body.rebalance,
        strategy_parameters=parameters,
        risk_limits=effective_risk,
    )
    try:
        run = service.run(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_friendly_error(exc))
    except Exception as exc:  # noqa: BLE001 - 引擎内部错误统一转 422
        raise HTTPException(status_code=422, detail=_friendly_error(exc))

    result = backtest_run_to_result(run, names=security_names())
    result["effective_config"] = {
        "strategy_reference": reference,
        "strategy_plugin": request.strategy_plugin,
        "strategy_parameters": request.strategy_parameters,
        "market": "当前股票池",
        "initial_capital": request.initial_cash,
        "max_positions": request.top_n,
        "rebalance": request.rebalance,
        "from_date": start, "to_date": end,
    }
    result = with_run_evidence(result)
    payload = json.dumps(result, ensure_ascii=False)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO backtests (user_id, strategy, market, from_date, to_date, status, result, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], body.strategy, body.market, start, end, "完成", payload, _now()),
        )
        bid = cur.lastrowid
    return {"id": bid, "status": "完成", "result": result, "created_at": _now()}


@router.get("/catalog", summary="可执行策略目录")
def backtest_catalog(user: dict = Depends(get_current_user)):
    service = build_backtest_service(user)
    user_plugins = getattr(service, "user_strategy_plugins", {})
    metadata = {m.plugin_name: m for m in service.available_strategies()}
    def item(m, value, label):
        return {"value": value, "label": label,
                "parameters": [asdict(p) for p in getattr(m, "parameters", ())],
                "defaults": service.default_request().strategy_parameters
                    if m.plugin_name == service.default_request().strategy_plugin else m.defaults()}
    items = [item(m, m.plugin_name, m.display_name)
             for m in metadata.values() if m.plugin_name not in user_plugins.values() and m.plugin_name != "rule_builder"]
    items.extend(item(metadata[plugin], f"user:{saved}", f"{metadata[plugin].display_name} · Python")
                 for saved, plugin in user_plugins.items())
    return {"items": items,
            "errors": list(getattr(service, "user_strategy_errors", ())),
            "default": service.default_request().strategy_plugin,
            "market": "当前股票池"}


@router.get("/{bid}", summary="单次回测详情")
def get_backtest(bid: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backtests WHERE id = ? AND user_id = ?", (bid, user["id"])
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回测不存在")
    result = with_run_evidence(json.loads(row["result"]) if row["result"] else {})
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
                "result": with_run_evidence(json.loads(r["result"]) if r["result"] else {}),
                "created_at": r["created_at"],
            }
        )
    return out
