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

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from typing import Any, Literal

from ..database import _now, get_conn
from ..quant.benchmark_view import benchmark_comparison, benchmark_options
from ..quant.compute import computing
from ..quant.markets import CURRENT_POOL, market_options, use_market
from ..quant.result_adapter import backtest_run_to_result
from ..quant.run_evidence import run_directory, with_run_evidence
from ..quant.runtime import (
    build_backtest_service,
    local_data_bounds,
    market_repository,
    security_names,
    user_risk_limits,
)
from ..quant import platform_ai
from ..routes.agent_lab import _ai_failure
from ..routes.auth import get_current_user
from quant_platform.ai_research.decisions import backtest_facts, review_backtest
from quant_platform.application.benchmarks import BENCHMARK_NAMES
from quant_platform.data.index_constituents import INDEX_UNIVERSES

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


# 只给管理员的策略：LLM 多智能体会按用户填的地址调用模型（可能带上平台的模型密钥），
# 每个调仓日对每只候选股票调用一次，不受每日 AI 次数限制。
ADMIN_ONLY_STRATEGIES = frozenset({"llm_multi_agent"})


def _resolve_plugin(service, strategy_name: str, user: dict | None = None) -> str:
    """Unknown strategies must never silently execute another strategy."""

    if strategy_name.startswith("user:"):
        # 以前的 Python 策略引用（研究记录里的“回到策略”、旧链接）。
        raise HTTPException(status_code=422, detail="Python 策略已经停用，请改用规则策略或因子组合策略。")
    for metadata in service.available_strategies():
        if strategy_name in (metadata.display_name, metadata.plugin_name):
            if metadata.plugin_name in ADMIN_ONLY_STRATEGIES and not (user or {}).get("is_admin"):
                raise HTTPException(status_code=403, detail="这个策略只对管理员开放。")
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
    if body.market != CURRENT_POOL and body.market not in INDEX_UNIVERSES:
        raise HTTPException(status_code=422, detail="不支持这个股票范围，请选择当前股票池或列表里的指数。")
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
            top_n=body.max_positions, rebalance=body.rebalance, market=body.market), user)

    service = build_backtest_service(user)
    use_market(service, body.market)
    reference = body.strategy.strip()
    plugin = _resolve_plugin(service, reference, user)
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
    with computing(user):
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
        "market": body.market,
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
    metadata = {m.plugin_name: m for m in service.available_strategies()}
    def item(m, value, label):
        return {"value": value, "label": label,
                "parameters": [asdict(p) for p in getattr(m, "parameters", ())],
                "defaults": service.default_request().strategy_parameters
                    if m.plugin_name == service.default_request().strategy_plugin else m.defaults()}
    items = [item(m, m.plugin_name, m.display_name)
             for m in metadata.values() if m.plugin_name != "rule_builder"
             and (user.get("is_admin") or m.plugin_name not in ADMIN_ONLY_STRATEGIES)]
    return {"items": items,
            "default": service.default_request().strategy_plugin,
            "market": CURRENT_POOL,
            "markets": market_options()}


@router.get("/{bid}", summary="单次回测详情")
def get_backtest(bid: int, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM backtests WHERE id = ? AND user_id = ?", (bid, user["id"])
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回测不存在")
    result = with_run_evidence(json.loads(row["result"]) if row["result"] else {})
    directory = run_directory(result)
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
        # 和基准的对比在查看时从运行目录读出，所以以前的回测也有。
        "benchmark": benchmark_comparison(directory),
        # 本地有行情的常用指数：结果页可以换一个指数来比较。
        "benchmark_options": benchmark_options(market_repository().read_table("benchmark_bars")) if directory else [],
    }


@router.get("/{bid}/benchmark", summary="把一次回测和另一个指数比较")
def backtest_benchmark(bid: int, symbol: str = Query(..., max_length=12), user: dict = Depends(get_current_user)):
    if symbol not in BENCHMARK_NAMES:
        raise HTTPException(status_code=422, detail="不支持的基准指数")
    with get_conn() as conn:
        row = conn.execute("SELECT result FROM backtests WHERE id = ? AND user_id = ?", (bid, user["id"])).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回测不存在")
    directory = run_directory(json.loads(row["result"]) if row["result"] else {})
    comparison = benchmark_comparison(directory, symbol, market_repository().read_table("benchmark_bars"))
    if comparison is None:
        raise HTTPException(status_code=404, detail=f"本地没有{BENCHMARK_NAMES[symbol]}在这段时间的行情，请先在「数据更新」里更新基准指数。")
    return comparison


# --------------------------------------------------------------------------- #
# AI 评估：决策模型 Jev 根据这次回测自己的数字估计风险等级和过度拟合的可能
# --------------------------------------------------------------------------- #


def _saved_review(bid: int, user: dict) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT review, created_at FROM ai_reviews WHERE backtest_id = ? AND user_id = ?", (bid, user["id"])).fetchone()
    return {**json.loads(row["review"]), "created_at": row["created_at"]} if row else None


@router.get("/{bid}/ai-review", summary="这次回测的 AI 评估（没有评估过时为空）")
def backtest_ai_review(bid: int, user: dict = Depends(get_current_user)):
    return {"review": _saved_review(bid, user), "available": platform_ai.decision_client() is not None,
            "usage": platform_ai.usage(user, "review")}


@router.post("/{bid}/ai-review", summary="让 AI 评估这次回测：风险等级、在新数据上做不到的可能")
def backtest_ai_review_run(bid: int, user: dict = Depends(get_current_user)):
    with computing(user):
        return _run_ai_review(bid, user)


def _run_ai_review(bid: int, user: dict):
    saved = _saved_review(bid, user)
    if saved is not None:
        return {"review": saved, "available": True, "usage": platform_ai.usage(user, "review")}  # 评估过：不再调用、不再计数
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM backtests WHERE id = ? AND user_id = ?", (bid, user["id"])).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回测不存在")
    client = platform_ai.decision_client()
    if client is None:
        raise HTTPException(status_code=422, detail="平台还没有配置决策模型，暂时不能评估。")
    result = with_run_evidence(json.loads(row["result"]) if row["result"] else {})
    facts = backtest_facts({"from_date": row["from_date"], "to_date": row["to_date"]}, result, benchmark_comparison(run_directory(result)))
    try:
        with platform_ai.quota_call(user, "review"):
            review = review_backtest(client, facts)
    except platform_ai.QuotaExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"AI 评估没有完成（{_ai_failure(exc)}），这次不计入次数。") from exc
    review["facts"] = [fact.to_dict() for fact in facts]
    with get_conn() as conn:
        conn.execute("INSERT OR REPLACE INTO ai_reviews (user_id, backtest_id, review, created_at) VALUES (?,?,?,?)",
                     (user["id"], bid, json.dumps(review, ensure_ascii=False), _now()))
    return {"review": _saved_review(bid, user), "available": True, "usage": platform_ai.usage(user, "review")}
