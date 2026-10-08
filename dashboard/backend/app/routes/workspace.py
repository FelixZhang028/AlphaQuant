"""
功能台聚合路由：把 FellowQuant_v3 工作台的各功能模块以 REST 形式聚合到本后端。

模块覆盖（与 v3 工作台对应）：
- 策略创作中心 / 自然语言建策略 / 零代码策略工作台 / 自定义策略(Python)
- 因子研究室 / 智能体分析台
- 单次回测与复盘（复用 backtests）/ 参数优化与稳健性验证 / 回测记录库
- 数据管理 / XTick 数据服务 / 风险管理 / 模拟交易 / 股票池管理

说明：与现有 stats/backtests 一致，当前业务数据为「可复现的模拟数据」，
替换真实数据源时只需改每个 endpoint 的取数逻辑，模型结构保持不变。
"""
from __future__ import annotations

import json
import math
import random
import re
from dataclasses import replace as dc_replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..database import _now, get_conn
from ..quant.result_adapter import backtest_run_to_result, factor_report_to_dict
from ..quant.runtime import (
    BACKEND_ROOT,
    CONFIG_PATH,
    DATA_UPDATE_LOCK,
    RUNTIME_ROOT,
    _backend_cwd,
    available_trading_days,
    build_backtest_service,
    build_data_center_service,
    build_factor_evaluator,
    build_factor_registry,
    local_data_bounds,
    market_repository,
    security_names,
    user_risk_limits,
    user_universe_symbols,
)
from ..quant.rules import (
    INDICATOR_TO_QUANT as _FRONTEND_INDICATORS,
    OPERATOR_TO_QUANT as _FRONTEND_OPERATORS,
    definition_to_frontend,
    definition_to_quant,
)
from ..quant.symbols import to_bare, to_canonical
from ..routes.agent_lab import _llm_store
from ..routes.auth import get_current_user
from quant_platform.agents_bridge.data_credentials import DataCredentialStore
from quant_platform.agents_bridge.llm_settings import PROVIDER_CATALOG
from quant_platform.application.strategy_studio_service import (
    StrategyPackage,
    StrategyStudioService,
)
from quant_platform.application.benchmarks import BENCHMARKS
from quant_platform.application.factor_research_service import research_combination
from quant_platform.core.exceptions import ConfigurationError
from quant_platform.factors.combine import (
    CompositeFactor,
    correlation_matrix,
    drop_highly_correlated,
)
from quant_platform.strategies.nl_builder import NLStrategyBuilder, definition_explanation
from quant_platform.strategies.rule_schema import (
    INDICATOR_LABELS,
    OPERATOR_LABELS,
    RuleStrategyDefinition,
)
from quant_platform.strategies.templates import beginner_templates
from quant_platform.web.factor_fields import field_description
from quant_platform.web.security_names import xtick_security_names
from quant_platform.jev import JevClient, ChoiceRequest, NoulRequest, ScoreRequest
from quant_platform.weknora import WeKnoraClient
from trading_agents.config import TradingConfig
from trading_agents.llm import create_llm_client

router = APIRouter(prefix="/api/v1", tags=["workspace"])

# --------------------------------------------------------------------------- #
# 因子库展示：逻辑分类（迁移自 AlphaQuant web/factor_library.py）
# --------------------------------------------------------------------------- #

_FACTOR_LOGICAL_CATEGORIES = {
    "动量": "动量与趋势",
    "反转": "反转与价格位置",
    "波动": "波动与风险",
    "量价": "K线与量价关系",
    "K线": "K线与量价关系",
    "技术": "反转与价格位置",
}
_FACTOR_CATEGORY_OVERRIDES = {
    "amount_change_20": "成交与流动性",
    "volume_ratio_5": "成交与流动性",
    "high_distance_20": "反转与价格位置",
    "bias_10": "反转与价格位置",
    "amplitude_20": "波动与风险",
}


def factor_logical_category(factor: Any) -> str:
    """按投资逻辑归并因子类别，自定义因子按算子归类。"""

    if factor.source == "自定义":
        operator = getattr(factor, "operator", "")
        return {
            "momentum": "动量与趋势",
            "bias": "反转与价格位置",
            "sma": "基础行情特征",
            "ma_ratio": "动量与趋势",
            "rolling_std": "波动与风险",
            "volatility": "波动与风险",
            "pv_corr": "K线与量价关系",
        }.get(operator, "未分类")
    return _FACTOR_CATEGORY_OVERRIDES.get(
        factor.name, _FACTOR_LOGICAL_CATEGORIES.get(factor.category, factor.category)
    )

# --------------------------------------------------------------------------- #
# 共用：可复现模拟回测
# --------------------------------------------------------------------------- #


def _sim_equity(seed: int, steps: int = 60) -> list[float]:
    rng = random.Random(seed)
    equity = [1_000_000.0]
    for _ in range(steps):
        ret = rng.gauss(0.004, 0.016)
        equity.append(max(equity[-1] * (1 + ret), 1000.0))
    return equity


def _sim_metrics(equity: list[float]) -> dict[str, Any]:
    total_return = (equity[-1] - equity[0]) / equity[0]
    peak, max_dd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)
    rets = [(equity[i] / equity[i - 1] - 1) for i in range(1, len(equity)) if equity[i - 1] > 0]
    mean = sum(rets) / len(rets) if rets else 0
    var = sum((r - mean) ** 2 for r in rets) / len(rets) if rets else 0
    std = math.sqrt(var)
    sharpe = (mean / std) * math.sqrt(252) if std > 0 else 0
    sortino_std = math.sqrt(sum((min(r, 0) ** 2 for r in rets)) / len(rets)) if rets else 0
    sortino = (mean / sortino_std) * math.sqrt(252) if sortino_std > 0 else 0
    calmar = (mean * 252) / (max_dd if max_dd > 0 else 1)
    wins = sum(1 for r in rets if r > 0)
    local_rng = random.Random(abs(hash((equity[0] if equity else 1, len(equity)))))
    return {
        "equity": [round(v, 2) for v in equity],
        "final_equity": round(equity[-1], 2),
        "total_return": round(total_return * 100, 2),
        "annual_return": round(mean * 252 * 100, 2),
        "max_drawdown": round(max_dd * 100, 2),
        "sharpe": round(sharpe, 2),
        "sortino": round(sortino, 2),
        "calmar": round(calmar, 2),
        "win_rate": round((wins / len(rets) * 100) if rets else 0, 2),
        "fills": local_rng.randint(20, 120),
        "orders": local_rng.randint(24, 140),
    }


def _stamp() -> str:
    return _now()


# --------------------------------------------------------------------------- #
# 1. 策略创作中心 / 零代码策略工作台 / 自然语言建策略
# --------------------------------------------------------------------------- #

_BUILTIN_INDICATORS = {name: INDICATOR_LABELS[quant] for name, (quant, _) in _FRONTEND_INDICATORS.items()}
_OPERATORS = {name: OPERATOR_LABELS[quant] for name, quant in _FRONTEND_OPERATORS.items()}
_FREQUENCIES = ["daily", "weekly", "monthly"]
_DIRECTIONS = ["descending", "ascending"]
_STYLES = ["conservative", "balanced", "aggressive"]


class DefinitionIn(BaseModel):
    strategy_id: str | None = None
    name: str = Field("", max_length=80)
    description: str = ""
    entry_logic: str = Field("all", description="all / any")
    entry_rules: list[dict[str, Any]] = []
    ranking: dict[str, Any] | None = None


class PackageIn(BaseModel):
    definition: DefinitionIn
    top_n: int = Field(5, ge=1, le=50)
    rebalance: str = Field("weekly")
    source: str = Field("visual_builder")


class CopyIn(BaseModel):
    name: str | None = None


def _describe(definition: dict[str, Any], top_n: int, rebalance: str) -> str:
    freq = {"daily": "每日", "weekly": "每周", "monthly": "每月"}.get(rebalance, rebalance)
    logic = "同时满足" if definition.get("entry_logic") == "all" else "满足任一"
    rules = definition.get("entry_rules") or []
    parts = []
    for i, rule in enumerate(rules[:6], 1):
        left = rule.get("left", {})
        op = _OPERATORS.get(rule.get("operator", ""), rule.get("operator", ""))
        val = rule.get("value")
        if val is not None:
            parts.append(f"条件{i}：{left.get('name', '指标')} {op} {val}")
        else:
            right = rule.get("right", {})
            parts.append(f"条件{i}：{left.get('name', '指标')} {op} {right.get('name', '指标')}")
    ranking = definition.get("ranking") or {}
    rank_txt = f"按{ranking.get('indicator', {}).get('name', '指标')}{'从高到低' if ranking.get('direction') == 'descending' else '从低到高'}排序"
    body = "；".join(parts) if parts else "无附加条件"
    return f"{freq}调仓，{logic}{body}；{rank_txt}，等权持有前 {top_n} 只，不在条件内的持仓自动卖出。"


def _package_row_to_dict(r) -> dict[str, Any]:
    canonical = json.loads(r["definition"])
    definition = definition_to_frontend(canonical)
    try:
        rule_def = RuleStrategyDefinition.from_mapping(canonical)
        describe_text = rule_def.describe(top_n=r["top_n"], rebalance=r["rebalance"])
    except ConfigurationError:
        describe_text = _describe(definition, r["top_n"], r["rebalance"])
    return {
        "package_id": r["package_id"],
        "name": r["name"],
        "definition": definition,
        "top_n": r["top_n"],
        "rebalance": r["rebalance"],
        "source": r["source"],
        "created_at": r["created_at"],
        "describe_text": describe_text,
    }


@router.get("/packages", summary="策略包列表")
def list_packages(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM strategy_packages WHERE user_id = ? ORDER BY id DESC", (user["id"],)
        ).fetchall()
    return {"items": [_package_row_to_dict(r) for r in rows], "total": len(rows)}


@router.post("/packages", status_code=status.HTTP_201_CREATED, summary="保存策略包")
def create_package(body: PackageIn, user: dict = Depends(get_current_user)):
    definition = body.definition.model_dump()
    if not definition.get("name"):
        definition["name"] = "我的策略"
    if not definition.get("strategy_id"):
        definition["strategy_id"] = f"strategy_{random.Random().randint(0, 0xFFFFFFFF):08x}"
    canonical = definition_to_quant(definition)
    try:
        rule_def = RuleStrategyDefinition.from_mapping(canonical)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
    package_id = f"{re.sub(r'[^A-Za-z0-9_]', '', rule_def.strategy_id)[:24]}-{random.Random().randint(0, 0xFFFFFFFF):08x}"
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO strategy_packages (user_id, package_id, name, definition, top_n, rebalance, source, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], package_id, rule_def.name, json.dumps(rule_def.to_dict(), ensure_ascii=False),
             body.top_n, body.rebalance, body.source, _now()),
        )
        row = conn.execute(
            "SELECT * FROM strategy_packages WHERE package_id = ? AND user_id = ?", (package_id, user["id"])
        ).fetchone()
    return _package_row_to_dict(row)


@router.get("/packages/{package_id}", summary="策略包详情")
def get_package(package_id: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_packages WHERE package_id = ? AND user_id = ?", (package_id, user["id"])
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="策略包不存在")
    return _package_row_to_dict(row)


@router.post("/packages/{package_id}/copy", status_code=status.HTTP_201_CREATED, summary="复制策略包")
def copy_package(package_id: str, body: CopyIn | None = None, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_packages WHERE package_id = ? AND user_id = ?", (package_id, user["id"])
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="策略包不存在")
        definition = json.loads(row["definition"])
        new_name = (body.name if body and body.name else None) or f"{row['name']}（副本）"
        new_id = f"{re.sub(r'[^A-Za-z0-9_]', '', definition.get('strategy_id') or 'strategy')[:20]}-{random.Random().randint(0, 0xFFFFFFFF):08x}"
        conn.execute(
            "INSERT INTO strategy_packages (user_id, package_id, name, definition, top_n, rebalance, source, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], new_id, new_name, row["definition"], row["top_n"], row["rebalance"],
             f"copy:{package_id}", _now()),
        )
        new_row = conn.execute(
            "SELECT * FROM strategy_packages WHERE package_id = ? AND user_id = ?", (new_id, user["id"])
        ).fetchone()
    return _package_row_to_dict(new_row)


@router.delete("/packages/{package_id}", status_code=status.HTTP_204_NO_CONTENT, summary="删除策略包")
def delete_package(package_id: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM strategy_packages WHERE package_id = ? AND user_id = ?", (package_id, user["id"])
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="策略包不存在")
    return None


@router.post("/packages/preflight", summary="回测前预检")
def preflight_package(body: PackageIn, user: dict = Depends(get_current_user)):
    definition = body.definition.model_dump()
    if not definition.get("strategy_id"):
        definition["strategy_id"] = f"strategy_{random.Random().randint(0, 0xFFFFFFFF):08x}"
    try:
        package = _package_from_definition(definition, body.top_n, body.rebalance, body.source)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
    available_days = available_trading_days()
    warnings = list(StrategyStudioService.preflight(package, available_days=available_days))
    return {"warnings": warnings, "minimum_history_days": package.definition.minimum_history_days}


@router.get("/packages/{package_id}/risk-score", summary="AI 策略风险评估（Jev Score）")
def package_risk_score(package_id: str, user: dict = Depends(get_current_user)):
    """用 Jev Score 对策略包做风险等级评分，返回 0-100 风险分与等级分布。"""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_packages WHERE package_id = ? AND user_id = ?", (package_id, user["id"])
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="策略包不存在")
    definition = json.loads(row["definition"])
    top_n = row["top_n"]
    rebalance = row["rebalance"]
    rules = definition.get("entry_rules") or []
    rule_count = len(rules)
    # 构造决策问题：把策略特征浓缩成自然语言
    freq = {"daily": "每日", "weekly": "每周", "monthly": "每月"}.get(rebalance, rebalance)
    question = (
        f"评估以下量化策略的风险等级：持有前 {top_n} 只股票，{freq}调仓，"
        f"包含 {rule_count} 条入场规则。请综合考虑集中度、调仓频率和规则复杂度给出风险评分。"
    )
    levels = ["低风险", "中低风险", "中等风险", "中高风险", "高风险"]
    client = _jev_client(user["id"])
    try:
        resp = client.score(ScoreRequest(question=question, levels=levels))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_sanitize_detail(exc))
    score_100 = resp.to_score_0_100()
    # 给出文字解读
    if score_100 < 25:
        interpretation = "风险较低，适合稳健型配置"
    elif score_100 < 50:
        interpretation = "风险中低，需关注集中度"
    elif score_100 < 75:
        interpretation = "风险中等，建议配合止损规则"
    else:
        interpretation = "风险较高，建议降低集中度或缩短调仓周期"
    return {
        "score_100": score_100,
        "score": resp.score,
        "level_probabilities": resp.level_probabilities,
        "confidence": resp.confidence,
        "levels": levels,
        "interpretation": interpretation,
        "mock": resp.mock,
    }


@router.post("/packages/{package_id}/backtest", status_code=status.HTTP_201_CREATED, summary="运行策略包回测")
def backtest_package(package_id: str, body: dict[str, Any] | None = None, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM strategy_packages WHERE package_id = ? AND user_id = ?", (package_id, user["id"])
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="策略包不存在")
    body = body or {}

    if not local_data_bounds():
        raise HTTPException(status_code=409, detail="本地暂无行情数据，请先在数据管理中下载。")
    start, end = _clamped_range(str(body.get("from_date") or body.get("start_date") or ""),
                                str(body.get("to_date") or body.get("end_date") or ""))
    initial_cash = float(body.get("initial_cash") or 1_000_000)

    service = build_backtest_service(user)
    studio = StrategyStudioService(service)
    source = str(row["source"] or "")
    if source.startswith("template:"):
        # 模板快速回测：使用 AlphaQuant 官方模板预设（style 控制风格），
        # top_n / rebalance 沿用用户在模板页设置的值。
        template_id = source.split(":", 1)[1]
        style = str(body.get("style") or "balanced")
        try:
            package = studio.template_package(template_id, style)
        except (ValueError, ConfigurationError) as exc:
            raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
        package = dc_replace(package, top_n=row["top_n"], rebalance=row["rebalance"])
    else:
        try:
            package = _package_from_definition(
                json.loads(row["definition"]), row["top_n"], row["rebalance"], row["source"]
            )
        except ConfigurationError as exc:
            raise HTTPException(status_code=422, detail=f"策略定义无效：{_sanitize_detail(exc)}")

    base = dc_replace(
        service.default_request(),
        start_date=start,
        end_date=end,
        initial_cash=initial_cash,
        risk_limits=user_risk_limits(user["id"]),
    )
    try:
        run = studio.run(package, base_request=base)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_friendly_engine_error(exc))
    except Exception as exc:  # noqa: BLE001 - 回测引擎内部错误统一转 422
        raise HTTPException(status_code=422, detail=_friendly_engine_error(exc))

    result = backtest_run_to_result(run, names=security_names())
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO backtests (user_id, strategy, market, from_date, to_date, status, result, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (user["id"], row["name"], "沪深300", start.isoformat(), end.isoformat(), "完成",
             json.dumps(result, ensure_ascii=False), _now()),
        )
        bid = cur.lastrowid
    return {"id": bid, "run_id": result["run_id"], "status": "完成", "summary": result}


def _package_from_definition(definition: dict[str, Any], top_n: int, rebalance: str, source: str) -> StrategyPackage:
    """前端/已存定义 -> 可执行的 StrategyPackage（校验失败抛 ConfigurationError）。"""

    canonical = definition_to_quant(definition)
    if not canonical["strategy_id"]:
        canonical["strategy_id"] = f"strategy_{random.Random().randint(0, 0xFFFFFFFF):08x}"
    rule_def = RuleStrategyDefinition.from_mapping(canonical)
    package = StrategyPackage(
        package_id="inline",
        name=rule_def.name,
        definition=rule_def,
        top_n=int(top_n),
        rebalance=str(rebalance),
        source=str(source or "visual_builder"),
        created_at=datetime.now(UTC),
    )
    package.validate()
    return package


@router.get("/studio/options", summary="零代码工作台选项与模板目录")
def studio_options(user: dict = Depends(get_current_user)):
    templates = []
    for template in beginner_templates():
        preset = template.presets.get("balanced") or next(iter(template.presets.values()))
        templates.append({
            "template_id": template.template_id,
            "name": template.name,
            "summary": template.summary,
            "suitable_market": template.suitable_market,
            "main_risk": template.main_risk,
            "top_n": preset.top_n,
            "rebalance": preset.rebalance,
        })
    indicators = {
        frontend: INDICATOR_LABELS[quant]
        for frontend, (quant, _) in _FRONTEND_INDICATORS.items()
    }
    operators = {
        frontend: OPERATOR_LABELS[quant]
        for frontend, quant in _FRONTEND_OPERATORS.items()
    }
    return {
        "templates": templates,
        "indicators": indicators,
        "operators": operators,
        "frequencies": _FREQUENCIES,
        "directions": _DIRECTIONS,
        "styles": _STYLES,
    }


# --------------------------------------------------------------------------- #
# 2. 自然语言建策略
# --------------------------------------------------------------------------- #

class NlGenerateIn(BaseModel):
    description: str = Field(..., min_length=3)
    provider: str = "mock"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    top_n: int = Field(5, ge=1, le=50)
    rebalance: str = "weekly"


@router.get("/nl/providers", summary="自然语言建策略：模型提供方目录")
def nl_providers(user: dict = Depends(get_current_user)):
    store = _llm_store(user["id"])
    ordered = ["mock", *[key for key in PROVIDER_CATALOG if key not in {"mock", "openrouter"}]]
    providers = []
    for key in ordered:
        spec = PROVIDER_CATALOG[key]
        resolved = store.resolve(key)
        providers.append(
            {
                "key": spec.key,
                "display_name": spec.display_name,
                "default_base_url": resolved["base_url"],
                "models": list(spec.models),
                "default_model": resolved["model"],
                "requires_key": spec.requires_key,
                "api_key_configured": bool(resolved["api_key"]),
            }
        )
    return {"providers": providers, "default_provider": store.get_default_provider()}


@router.post("/nl/generate", summary="自然语言生成结构化策略规则（真实 LLM，校验失败自动修复重试）")
def nl_generate(body: NlGenerateIn, user: dict = Depends(get_current_user)):
    store = _llm_store(user["id"])
    provider = (
        body.provider if body.provider in PROVIDER_CATALOG else store.get_default_provider()
    )
    if provider == "openrouter":
        raise HTTPException(status_code=422, detail="Jev 为决策模型，请在 AI 决策中心使用")
    spec = PROVIDER_CATALOG[provider]
    resolved = store.resolve(provider)
    if body.base_url.strip():
        resolved["base_url"] = _service_url(body.base_url)
    if body.api_key.strip():
        resolved["api_key"] = body.api_key.strip()
    if body.model.strip():
        resolved["model"] = body.model.strip()
    if spec.requires_key and not resolved["api_key"]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{spec.display_name} 未配置 API Key：请先在「智能体分析台 → 配置模型」"
                "保存密钥，或改用 Mock 离线生成。"
            ),
        )
    try:
        client = create_llm_client(
            provider,
            model=resolved["model"] or spec.default_model,
            base_url=resolved["base_url"] or None,
            api_key=resolved["api_key"] or None,
            env_key_name=TradingConfig.env_key_name(provider),
        )
        definition = NLStrategyBuilder(client).generate(body.description)
    except ConfigurationError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - LLM 调用异常统一转 422
        raise HTTPException(status_code=422, detail=f"生成失败：{_sanitize_detail(exc)}") from exc
    return {
        "definition": definition_to_frontend(definition.to_dict()),
        "explanation": definition_explanation(
            definition, top_n=body.top_n, rebalance=body.rebalance
        ),
        "minimum_history_days": definition.minimum_history_days,
    }


# --------------------------------------------------------------------------- #
# 3. 自定义策略（Python）
# --------------------------------------------------------------------------- #

_DISALLOWED_IMPORTS = ("subprocess", "socket", "pickle", "ctypes", "multiprocessing")


class UserStrategyIn(BaseModel):
    code: str = Field(..., min_length=1)
    display_name: str = ""
    description: str = ""
    source: str = "editor"
    risk_acknowledged: bool = False


def _analyze(code: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for line_no, line in enumerate(code.splitlines(), 1):
        for mod in _DISALLOWED_IMPORTS:
            if re.search(rf"\b(import|from)\s+{mod}\b", line):
                blockers.append({"code": "forbidden_import", "severity": "error", "message": f"禁用模块：{mod}", "line": line_no})
        if "lookahead" in line or "未来函数" in line:
            warnings.append({"code": "future_function", "severity": "warning", "message": "疑似未来函数引用", "line": line_no})
    if "@register_strategy" not in code:
        blockers.append({"code": "no_register", "severity": "error", "message": "缺少 @register_strategy 装饰器", "line": 0})
    return blockers, warnings


def _parse_params(code: str) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    if "fast" in code.lower():
        params.append({"name": "fast", "label": "快线周期", "kind": "integer", "default": 5, "minimum": 1, "maximum": 250})
    if "slow" in code.lower():
        params.append({"name": "slow", "label": "慢线周期", "kind": "integer", "default": 20, "minimum": 1, "maximum": 500})
    if "momentum" in code.lower() or "lookback" in code.lower():
        params.append({"name": "lookback", "label": "动量窗口", "kind": "integer", "default": 20, "minimum": 1, "maximum": 250})
    if "threshold" in code.lower():
        params.append({"name": "threshold", "label": "阈值", "kind": "number", "default": 0.0})
    if not params:
        params.append({"name": "window", "label": "观察周期", "kind": "integer", "default": 20, "minimum": 1, "maximum": 500})
    return params


@router.post("/user-strategies/preview", summary="校验并预览自定义策略代码")
def user_strategy_preview(body: UserStrategyIn, user: dict = Depends(get_current_user)):
    blockers, warnings = _analyze(body.code)
    plugin_name = re.sub(r"[^A-Za-z0-9_]", "", body.display_name.lower() or "custom_strategy")
    return {
        "plugin_name": plugin_name or "custom_strategy",
        "display_name": body.display_name or "自定义策略",
        "description": body.description,
        "parameters": _parse_params(body.code),
        "safety_report": {"blocked": bool(blockers), "blockers": blockers, "warnings": warnings},
        "errors": [],
    }


@router.post("/user-strategies", status_code=status.HTTP_201_CREATED, summary="保存自定义策略")
def user_strategy_save(body: UserStrategyIn, user: dict = Depends(get_current_user)):
    blockers, warnings = _analyze(body.code)
    if blockers:
        raise HTTPException(status_code=422, detail={"blockers": blockers})
    if warnings and not body.risk_acknowledged:
        raise HTTPException(status_code=409, detail="存在安全风险提示，请先勾选风险确认。")
    plugin_name = re.sub(r"[^A-Za-z0-9_]", "", body.display_name.lower() or "custom_strategy") or "custom_strategy"
    params = _parse_params(body.code)
    now = _now()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO user_strategies (user_id, plugin_name, display_name, description, source, code, parameters, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id, plugin_name) DO UPDATE SET display_name=excluded.display_name, description=excluded.description, code=excluded.code, parameters=excluded.parameters, updated_at=excluded.updated_at",
            (user["id"], plugin_name, body.display_name or "自定义策略", body.description, body.source, body.code,
             json.dumps(params, ensure_ascii=False), now, now),
        )
    return {"plugin_name": plugin_name, "display_name": body.display_name or "自定义策略",
            "description": body.description, "source": body.source, "parameters": params}


@router.get("/user-strategies", summary="列出自定义策略")
def user_strategy_list(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT plugin_name, display_name, description, source, parameters, created_at, updated_at FROM user_strategies WHERE user_id = ? ORDER BY updated_at DESC",
            (user["id"],),
        ).fetchall()
    return {"strategies": [
        {"plugin_name": r["plugin_name"], "display_name": r["display_name"], "description": r["description"],
         "source": r["source"], "parameters": json.loads(r["parameters"]), "created_at": r["created_at"], "updated_at": r["updated_at"]}
        for r in rows
    ]}


@router.delete("/user-strategies/{plugin_name}", status_code=status.HTTP_204_NO_CONTENT, summary="删除自定义策略")
def user_strategy_delete(plugin_name: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM user_strategies WHERE plugin_name = ? AND user_id = ?", (plugin_name, user["id"])
        )
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="策略不存在")
    return None


# --------------------------------------------------------------------------- #
# 4. 因子研究室
# --------------------------------------------------------------------------- #


def _clamped_range(start_str: str, end_str: str) -> tuple[date, date]:
    """把请求区间收敛到本地数据可用范围（前端默认区间常超出本地数据）。"""

    bounds = local_data_bounds()
    if bounds is None:
        raise HTTPException(status_code=409, detail="本地暂无行情数据，请先在数据管理中下载。")
    local_start, local_end = bounds

    def _parse(value: str, default: date) -> date:
        try:
            return date.fromisoformat(str(value or ""))
        except ValueError:
            return default

    start = max(_parse(start_str, local_start), local_start)
    end = min(_parse(end_str, local_end), local_end)
    if start >= end:
        raise HTTPException(
            status_code=422,
            detail=f"所选区间与本地数据（{local_start} ~ {local_end}）无交集。",
        )
    return start, end


def _factor_symbols(user: dict) -> list[str] | None:
    return user_universe_symbols(user["id"]) or None


# 引擎英文报错 -> 中文提示（避免把 "No daily bars available for backtest" 直接抛给用户）
_ENGINE_ERROR_MESSAGES = {
    "No daily bars available for backtest": "本地没有所选区间的日线数据，请先在数据管理中下载行情。",
    "No trading calendar data in requested range": "所选区间没有交易日历数据，请先在数据管理中下载数据。",
    "MISSING_CORPORATE_ACTION": "有股票在回测期间发生除权除息但缺少分红明细，请在数据管理中更新公司行为数据。",
    "INVALID_CORPORATE_ACTION_DATE": "公司行为日期不在交易日历中，请更新交易日历数据。",
    "MISSING_DELISTING_SETTLEMENT": "有股票退市但缺少退市结算数据，请在数据管理中更新退市信息。",
    "MISSING_EQUITY": "净值记录缺少账户权益数据。",
    "MISSING_ADJ_FACTOR": "缺少复权因子数据，请在数据管理中下载复权数据。",
}

import re as _re


def _sanitize_detail(exc: Exception) -> str:
    """清洗异常信息，去除技术细节，只保留用户可读消息。"""
    text = str(exc).strip()
    if not text:
        return "操作失败，请检查输入或稍后重试"
    # 去除 Python 异常类名前缀：ValueError: xxx
    text = _re.sub(r"^[A-Z]\w*(?:Error|Exception|Warning|Interrupt):\s*", "", text)
    # 去除引擎错误码前缀：MISSING_CORPORATE_ACTION: xxx / INVALID_DATE: xxx
    text = _re.sub(r"^[A-Z][A-Z_]{2,}:\s*", "", text)
    # 去除文件路径和行号
    text = _re.sub(r'File ["\'][^"\']+["\'],\s*line\s*\d+[^)]*', "", text)
    text = _re.sub(r"[\w./\\-]+\.py:\d+:\s*", "", text)
    # 去除 traceback 残留
    if "Traceback" in text:
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("Traceback") and not l.startswith('  File')]
        text = lines[-1] if lines else ""
    text = text.strip()
    if not text or len(text) < 2:
        return "操作失败，请检查输入或稍后重试"
    return text


def _friendly_engine_error(exc: Exception) -> str:
    text = str(exc)
    for english, chinese in _ENGINE_ERROR_MESSAGES.items():
        if english in text:
            return chinese
    return f"回测失败：{_sanitize_detail(exc)}"


class FactorEvalIn(BaseModel):
    factor_name: str
    start_date: str = ""
    end_date: str = ""
    horizon: int = Field(5, ge=1, le=20)
    n_groups: int = Field(5, ge=5, le=10)


class FactorCompositeIn(BaseModel):
    factor_names: list[str]
    weight_mode: str = "equal"
    weights: dict[str, float] | None = None
    winsorize: bool = True
    zscore: bool = False
    fill_method: str = "drop"
    corr_threshold: float = 0.7
    start_date: str = ""
    end_date: str = ""
    horizon: int = 5
    n_groups: int = 5


class FactorResearchIn(BaseModel):
    factor_names: list[str]
    train_start: str = ""
    train_end: str = ""
    test_start: str = ""
    test_end: str = ""
    weight_mode: str = "equal"  # equal | manual | ic
    weights: dict[str, float] | None = None
    clip: bool = True
    missing: str = "drop"  # drop | median
    horizon: int = Field(5, ge=1, le=20)
    n_groups: int = Field(5, ge=5, le=10)


class CustomFactorIn(BaseModel):
    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    display_name: str = ""
    description: str = ""
    field: str
    operator: str
    window: int = Field(..., ge=1)
    window2: int | None = None
    direction: int = Field(1, ge=-1, le=1)


@router.get("/factors", summary="因子库")
def list_factors(user: dict = Depends(get_current_user)):
    registry = build_factor_registry(user)
    factors = [
        {
            "name": factor.name,
            "display_name": factor.display_name or factor.name,
            "category": factor.category,
            "logical_category": factor_logical_category(factor),
            "source": factor.source,
            "feature_type": factor.feature_type,
            "description": factor.description,
            "formula": factor.formula,
            "required_fields": [
                {"field": field, "label": field_description(field)[0], "note": field_description(field)[1]}
                for field in factor.required_fields
            ],
            "min_history": int(factor.min_history),
            "direction": factor.direction,
            "version": factor.version,
            "source_url": factor.source_url or "",
        }
        for factor in registry.list()
    ]
    return {"factors": factors}


@router.post("/factors/evaluate", summary="单因子评估")
def factor_evaluate(body: FactorEvalIn, user: dict = Depends(get_current_user)):
    registry = build_factor_registry(user)
    try:
        factor = registry.get(body.factor_name)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"因子不存在：{body.factor_name}")
    start, end = _clamped_range(body.start_date, body.end_date)
    evaluator = build_factor_evaluator()
    try:
        report = evaluator.evaluate(
            factor, start, end, symbols=_factor_symbols(user),
            horizon=body.horizon, n_groups=body.n_groups,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
    return factor_report_to_dict(report)


@router.post("/factors/composite", summary="多因子合成并评估")
def factor_composite(body: FactorCompositeIn, user: dict = Depends(get_current_user)):
    if len(body.factor_names) < 2:
        raise HTTPException(status_code=400, detail="请至少选择两个因子进行合成")
    registry = build_factor_registry(user)
    components = []
    for name in body.factor_names:
        try:
            components.append(registry.get(name))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"因子不存在：{name}")
    start, end = _clamped_range(body.start_date, body.end_date)
    evaluator = build_factor_evaluator()
    symbols = _factor_symbols(user)

    # 权重：custom 用前端给的；equal 等权；ic 用各因子 |Rank IC| 加权。
    weights = body.weights or {name: 1.0 for name in body.factor_names}
    if body.weight_mode == "ic":
        weights = {}
        for item in components:
            report = evaluator.evaluate(
                item, start, end, symbols=symbols,
                horizon=body.horizon, n_groups=body.n_groups,
            )
            weights[item.name] = abs(report.rank_ic_mean) if report.rank_ic_mean == report.rank_ic_mean else 0.0
        if sum(weights.values()) <= 0:
            weights = {name: 1.0 for name in body.factor_names}

    # 相关性矩阵与高相关剔除（保留用户选择顺序中靠前的因子）。
    bars = evaluator.repository.get_daily_bars(symbols=symbols, end_date=end)
    frames = {item.name: item.compute(bars) for item in components}
    corr_frame = correlation_matrix(frames)
    corr: dict[str, dict[str, float]] = {}
    if not corr_frame.empty:
        for name in body.factor_names:
            corr[name] = {
                other: round(float(corr_frame.loc[name, other]), 3)
                for other in body.factor_names
            }
    dropped = drop_highly_correlated(
        corr_frame, threshold=body.corr_threshold, priority=body.factor_names
    )
    kept_components = [item for item in components if item.name not in dropped]
    if len(kept_components) < 2:
        raise HTTPException(
            status_code=422,
            detail="剔除高相关因子后成分不足两个，请更换因子组合或调高相关性阈值。",
        )
    kept_weights = {name: float(weights.get(name, 1.0)) for name in (i.name for i in kept_components)}
    composite = CompositeFactor(
        name="composite",
        display_name="合成因子",
        description="因子研究室多因子合成",
        components=tuple(kept_components),
        weights=kept_weights,
    )
    try:
        report = evaluator.evaluate(
            composite, start, end, symbols=symbols,
            horizon=body.horizon, n_groups=body.n_groups,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
    total_weight = sum(abs(v) for v in kept_weights.values()) or 1.0
    composite_spec = [
        {"name": item.name, "weight": round(kept_weights.get(item.name, 0.0) / total_weight, 4)}
        for item in kept_components
    ]
    return {
        "correlation_matrix": corr,
        "dropped_factors": dropped,
        "weights": weights,
        "composite_spec": composite_spec,
        "report": factor_report_to_dict(report),
    }


@router.post("/factors/research", summary="因子组合研究：训练期定权重，测试期比较")
def factor_research(body: FactorResearchIn, user: dict = Depends(get_current_user)):
    """迁移自 AlphaQuant factor_research_service：训练/测试集严格隔离的研究流程。"""

    if len(body.factor_names) < 2:
        raise HTTPException(status_code=400, detail="请至少选择两个因子进行研究")
    registry = build_factor_registry(user)
    components = []
    for name in body.factor_names:
        try:
            components.append(registry.get(name))
        except KeyError:
            raise HTTPException(status_code=404, detail=f"因子不存在：{name}")
    bounds = local_data_bounds()
    if bounds is None:
        raise HTTPException(status_code=409, detail="本地暂无行情数据，请先在数据管理中下载。")
    local_start, local_end = bounds

    def _parse(value: str, default: str) -> date:
        try:
            return date.fromisoformat(str(value or ""))
        except ValueError:
            return date.fromisoformat(default)

    # 各边界缺省时自动切分为：前 70% 训练 / 后 30% 测试，并收敛到本地数据范围。
    train_start = _parse(body.train_start, local_start.isoformat())
    test_end = _parse(body.test_end, local_end.isoformat())
    train_end = _parse(body.train_end, str(date.fromordinal(
        train_start.toordinal() + max(1, int((test_end.toordinal() - train_start.toordinal()) * 0.7))
    )))
    test_start = _parse(body.test_start, str(date.fromordinal(train_end.toordinal() + 1)))
    train_start = max(train_start, local_start)
    test_end = min(test_end, local_end)

    try:
        result = research_combination(
            market_repository(),
            tuple(components),
            train_start=train_start,
            train_end=train_end,
            test_start=test_start,
            test_end=test_end,
            mode=body.weight_mode,
            custom_weights=body.weights,
            clip=body.clip,
            missing=body.missing,
            horizon=body.horizon,
            n_groups=body.n_groups,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))

    corr: dict[str, dict[str, float]] = {}
    if not result.correlation.empty:
        for name in body.factor_names:
            corr[name] = {
                other: round(float(result.correlation.loc[name, other]), 3)
                for other in body.factor_names
                if other in result.correlation.columns
            }
    comparison = result.comparison.fillna(0.0).to_dict(orient="records")
    for row in comparison:
        for key, value in list(row.items()):
            if isinstance(value, float):
                row[key] = round(value, 4)
    return {
        "train_start": train_start.isoformat(),
        "train_end": train_end.isoformat(),
        "test_start": test_start.isoformat(),
        "test_end": test_end.isoformat(),
        "weights": {k: round(float(v), 4) for k, v in result.weights.items()},
        "correlation_matrix": corr,
        "comparison": comparison,
        "composite_spec": result.spec,
        "reports": {label: factor_report_to_dict(report) for label, report in result.reports.items()},
    }


@router.post("/factors/custom", status_code=status.HTTP_201_CREATED, summary="创建自定义因子")
def factor_custom_create(body: CustomFactorIn, user: dict = Depends(get_current_user)):
    if body.operator == "ma_ratio" and (not body.window2 or body.window2 <= body.window):
        raise HTTPException(status_code=422, detail="ma_ratio 算子的第二窗口需大于第一窗口")
    with get_conn() as conn:
        exists = conn.execute("SELECT id FROM custom_factors WHERE user_id = ? AND name = ?", (user["id"], body.name)).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="因子标识已存在")
        conn.execute(
            "INSERT INTO custom_factors (user_id, name, display_name, description, field, operator, window, window2, direction, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user["id"], body.name, body.display_name, body.description, body.field, body.operator, body.window,
             body.window2, body.direction, _now()),
        )
    return {"created": body.model_dump()}


@router.delete("/factors/custom/{name}", status_code=status.HTTP_204_NO_CONTENT, summary="删除自定义因子")
def factor_custom_delete(name: str, user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM custom_factors WHERE user_id = ? AND name = ?", (user["id"], name))
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="自定义因子不存在")
    return None


# --------------------------------------------------------------------------- #
# 5. 智能体分析台 —— 已迁移到 app/routes/agent_lab.py（真实 LLM 多智能体流水线）
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# 6. 参数优化与稳健性验证 / 回测记录库
# --------------------------------------------------------------------------- #

_OBJECTIVES = {"sharpe": "夏普比率", "annual_return": "年化收益", "calmar": "卡玛比率", "max_drawdown": "最大回撤"}


@router.get("/research/baselines", summary="可作为实验基线的成功回测")
def research_baselines(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, strategy, market, from_date, to_date, status, created_at FROM backtests WHERE user_id = ? AND status = '完成' ORDER BY id DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    return {"items": [
        {"run_id": f"run-{r['id']}", "strategy": r["strategy"], "market": r["market"], "from_date": r["from_date"],
         "to_date": r["to_date"], "created_at": r["created_at"], "display_label": f"{r['strategy']}｜{r['from_date']}~{r['to_date']}"}
        for r in rows
    ]}


class OptimizeIn(BaseModel):
    baseline_run_id: str = ""
    parameter_grid: dict[str, list[Any]] = {}
    objective: str = "sharpe"
    max_drawdown_limit: float = 0.30
    start_date: str = ""
    end_date: str = ""


@router.post("/research/optimize", summary="运行参数优化网格搜索（模拟）")
def research_optimize(body: OptimizeIn, user: dict = Depends(get_current_user)):
    grid = body.parameter_grid or {"window": [10, 20, 30], "threshold": [0.0, 0.05]}
    keys = list(grid)
    combos: list[dict[str, Any]] = []
    def _recurse(i: int, acc: dict[str, Any]):
        if i == len(keys):
            combos.append(dict(acc))
            return
        for v in grid[keys[i]]:
            acc[keys[i]] = v
            _recurse(i + 1, acc)
    _recurse(0, {})
    combos = combos[:100]
    rng = random.Random(abs(hash((user["id"], body.baseline_run_id, json.dumps(grid)))))
    results = []
    for idx, c in enumerate(combos):
        obj = round(rng.uniform(-0.1, 2.0), 3) if body.objective != "max_drawdown" else round(rng.uniform(0.05, 0.5), 3)
        dd = round(rng.uniform(0.05, 0.5), 3)
        eligible = dd <= body.max_drawdown_limit
        results.append({"rank": idx + 1, "eligible": eligible, "objective_value": obj,
                        "parameters": c, "max_drawdown": dd, "status": "SUCCESS", "run_id": f"run-opt-{idx}"})
    results.sort(key=lambda x: (not x["eligible"], -x["objective_value"]))
    for i, r in enumerate(results, 1):
        r["rank"] = i
    return {"optimization_id": f"opt-{_now()}", "objective": body.objective, "combination_count": len(combos), "results": results}


class WalkForwardIn(BaseModel):
    baseline_run_id: str = ""
    parameter_grid: dict[str, list[Any]] = {}
    objective: str = "sharpe"
    training_months: int = Field(12, ge=3)
    test_months: int = Field(3, ge=1)
    step_months: int = Field(3, ge=1)
    max_windows: int = Field(8, ge=1, le=24)
    start_date: str = ""
    end_date: str = ""


@router.post("/research/walk-forward", summary="运行滚动样本外验证（模拟）")
def research_walk_forward(body: WalkForwardIn, user: dict = Depends(get_current_user)):
    if body.step_months < body.test_months:
        raise HTTPException(status_code=400, detail="滚动步长不能小于测试月数")
    rng = random.Random(abs(hash((user["id"], body.baseline_run_id))))
    windows = []
    start = date.today() - timedelta(days=365 * 2)
    for w in range(body.max_windows):
        train_start = start
        train_end = train_start + timedelta(days=30 * body.training_months)
        test_start = train_end
        test_end = test_start + timedelta(days=30 * body.test_months)
        oos_ret = round(rng.gauss(0.03, 0.08), 4)
        windows.append({
            "window": w + 1, "train_start": train_start.isoformat(), "train_end": train_end.isoformat(),
            "test_start": test_start.isoformat(), "test_end": test_end.isoformat(),
            "train_run_id": f"run-wf-train-{w}", "test_run_id": f"run-wf-test-{w}",
            "selected_parameters": {"window": rng.choice([10, 20, 30])},
            "train_objective_value": round(rng.uniform(0.5, 2.0), 3),
            "test_cumulative_return": oos_ret, "test_max_drawdown": round(rng.uniform(0.05, 0.25), 3),
            "test_sharpe": round(rng.uniform(0.2, 2.0), 3), "status": "SUCCESS",
        })
        start = start + timedelta(days=30 * body.step_months)
    successful = [w for w in windows if w["status"] == "SUCCESS"]
    oos_cum = sum(w["test_cumulative_return"] for w in successful)
    positive = sum(1 for w in successful if w["test_cumulative_return"] > 0)
    worst_dd = min((w["test_max_drawdown"] for w in successful), default=0)
    return {
        "validation_id": f"wf-{_now()}", "window_count": len(windows),
        "summary": {
            "successful_windows": len(successful), "out_of_sample_cumulative_return": round(oos_cum, 4),
            "positive_window_ratio": round(positive / len(successful), 4) if successful else 0,
            "worst_window_drawdown": round(worst_dd, 4),
            "trust_warning": "固定股票池仍可能存在事后选股偏差，样本外结果不代表未来表现。",
        },
        "windows": windows,
    }


@router.get("/runs", summary="回测记录库列表")
def run_library(user: dict = Depends(get_current_user), strategy: str = "", run_kind: str = "", status: str = "", keyword: str = ""):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, strategy, market, from_date, to_date, status, result, created_at FROM backtests WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    items = []
    for r in rows:
        res = json.loads(r["result"]) if r["result"] else {}
        label = f"{r['strategy']}｜{r['from_date']}~{r['to_date']}｜{r['created_at'][:10]}"
        if keyword and keyword.lower() not in label.lower():
            continue
        items.append({"run_id": f"run-{r['id']}", "run_label": label, "run_kind": "single", "status": "SUCCESS" if r["status"] == "完成" else r["status"],
                      "validity_status": "VALID", "metrics_reliable": True, "legacy_unverified": False,
                      "strategy": r["strategy"], "start_date": r["from_date"], "end_date": r["to_date"],
                      "updated_at": r["created_at"], "cumulative_return": res.get("total_return"), "max_drawdown": res.get("max_drawdown"),
                      "sharpe": res.get("sharpe"), "sortino": res.get("sortino"), "calmar": res.get("calmar")})
    total = len(items)
    return {"items": items, "total": total,
            "stats": {"all": total, "success": total, "failed": 0, "legacy_unverified": 0, "experiment": 0}}


@router.post("/runs/compare", summary="对比 2~5 次回测")
def run_compare(body: dict[str, Any], user: dict = Depends(get_current_user)):
    run_ids = body.get("run_ids", [])
    if not 2 <= len(run_ids) <= 5:
        raise HTTPException(status_code=400, detail="请选择 2~5 次回测进行对比")
    comparison = []
    normalized_nav: dict[str, list[float]] = {}
    for rid in run_ids:
        seed = abs(hash((user["id"], rid)))
        equity = _sim_equity(seed)
        metrics = _sim_metrics(equity)
        base = equity[0]
        normalized_nav[rid] = [round(v / base, 4) for v in equity]
        comparison.append({"run_id": rid, "strategy": "策略", "cumulative_return": metrics["total_return"],
                           "max_drawdown": metrics["max_drawdown"], "sharpe": metrics["sharpe"],
                           "sortino": metrics["sortino"], "calmar": metrics["calmar"], "metrics_reliable": True})
    n = len(normalized_nav[run_ids[0]])
    nav_points = []
    for i in range(n):
        point = {"trade_date": f"2024-01-{i % 28 + 1:02d}"}
        for rid in run_ids:
            point[rid] = normalized_nav[rid][i]
        nav_points.append(point)
    return {"comparison": comparison, "normalized_nav": nav_points}


# --------------------------------------------------------------------------- #
# 6.5 可信度审计（迁移自 AlphaQuant audit_report.py + credibility.py）
# --------------------------------------------------------------------------- #


def _audit_run_row(run_ref: str, user: dict):
    """run-<id> -> 该用户的一条回测记录（含引擎持久化目录）。"""

    prefix, _, raw_id = str(run_ref).rpartition("-")
    if prefix != "run" or not raw_id.isdigit():
        raise HTTPException(status_code=400, detail="回测记录编号无效")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, strategy, from_date, to_date, status, result, created_at FROM backtests WHERE id = ? AND user_id = ?",
            (int(raw_id), user["id"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="回测记录不存在")
    result = json.loads(row["result"]) if row["result"] else {}
    return row, result


@router.get("/runs/audit", summary="可审计的回测记录列表")
def audit_run_list(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, strategy, from_date, to_date, status, result, created_at FROM backtests WHERE user_id = ? ORDER BY id DESC",
            (user["id"],),
        ).fetchall()
    items = []
    for r in rows:
        result = json.loads(r["result"]) if r["result"] else {}
        if not result.get("output_dir"):
            continue
        items.append({
            "run_id": f"run-{r['id']}",
            "run_label": f"{r['strategy']}｜{r['from_date']}~{r['to_date']}｜{r['created_at'][:10]}",
            "status": r["status"],
            "metrics_reliable": bool(result.get("metrics_reliable", True)),
        })
    return {"items": items}


@router.get("/runs/{run_ref}/audit", summary="回测可信度审计：五维评级与证据链")
def run_audit(run_ref: str, user: dict = Depends(get_current_user)):
    from quant_platform.backtest.credibility import audit_persisted_run
    from quant_platform.backtest.validity import load_persisted_validity

    row, result = _audit_run_row(run_ref, user)
    output_dir = Path(str(result.get("output_dir") or ""))
    if not output_dir.is_absolute():
        output_dir = Path(__file__).resolve().parents[2] / output_dir
    if not (output_dir / "summary.json").exists():
        raise HTTPException(status_code=404, detail="该记录的运行明细已不存在，无法审计")
    try:
        report = audit_persisted_run(output_dir)
        validity = load_persisted_validity(output_dir)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"读取运行记录失败：{_sanitize_detail(exc)}")

    dimensions = [
        {
            "key": d.key,
            "title": d.title,
            "status": d.status,
            "findings": [{"severity": f.severity, "message": f.message} for f in d.findings],
        }
        for d in report.dimensions
    ]
    # 审计假设表：从运行配置快照提取执行参数（迁移自 AlphaQuant audit_report）。
    assumptions = {}
    try:
        import yaml

        snapshot = yaml.safe_load((output_dir / "config.snapshot.yaml").read_text(encoding="utf-8")) or {}
        execution = snapshot.get("execution") or {}
        if isinstance(execution, dict) and isinstance(execution.get("execution"), dict):
            execution = execution["execution"]
        if isinstance(execution, dict):
            assumptions = {
                "historical_fees": execution.get("historical_fees"),
                "max_participation": execution.get("max_participation"),
                "slippage_rate": execution.get("slippage_rate"),
                "unknown_status_policy": execution.get("unknown_status_policy"),
            }
    except Exception:  # noqa: BLE001 - 快照缺失不影响评级本身
        pass
    return {
        "run_id": f"run-{row['id']}",
        "run_label": f"{row['strategy']}｜{row['from_date']}~{row['to_date']}｜{row['created_at'][:10]}",
        "grade": report.grade,
        "headline": report.headline,
        "dimensions": dimensions,
        "validity_status": report.validity_status,
        "metrics_reliable": report.metrics_reliable,
        "observations": report.observations,
        "maximum_calendar_gap_days": report.maximum_calendar_gap_days,
        "total_transaction_cost": report.total_transaction_cost,
        "transaction_cost_ratio": report.transaction_cost_ratio,
        "issues": [i for i in validity.get("issues", []) if isinstance(i, dict)],
        "assumptions": assumptions,
    }


# --------------------------------------------------------------------------- #
# 6.6 外部成交核查（迁移自 AlphaQuant forensics + external_audit）
# --------------------------------------------------------------------------- #

FORENSICS_TEMPLATE = (
    "日期,股票代码,买卖方向,数量（股）,成交价（未复权）\n2024-03-01,000001.SZ,买入,1000,10.50\n"
)


class ForensicsPreviewRequest(BaseModel):
    content: str = Field(..., description="粘贴的成交记录文本（CSV 或 Tab 分隔）")


class ForensicsCheckRequest(BaseModel):
    content: str = Field(..., description="粘贴的成交记录文本")
    mapping: dict[str, str] = Field(..., description="字段→列名映射")
    unit: str = Field(..., description="数量单位：股 或 手")
    basis: str = Field(..., description="价格口径：未复权 或 复权或不确定")


@router.get("/forensics/template", summary="下载成交记录模板")
def forensics_template():
    from fastapi.responses import Response

    return Response(
        content=FORENSICS_TEMPLATE.encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=成交记录模板.csv"},
    )


@router.post("/forensics/preview", summary="解析成交记录并返回列识别结果")
def forensics_preview(req: ForensicsPreviewRequest, user: dict = Depends(get_current_user)):
    from quant_platform.forensics.parsing import LABELS, detect_columns, header, read_material

    try:
        frame = read_material(req.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))
    mapping = detect_columns(frame)
    preview = frame.head(10).fillna("").to_dict(orient="records")
    # 转为 list 以便 JSON 序列化（index 为行号）
    row_numbers = frame.head(10).index.tolist()
    for rec, num in zip(preview, row_numbers):
        rec["__row__"] = num
    missing = [field for field in LABELS if field not in mapping]
    # 推断单位和价格口径
    quantity_header = header(mapping["quantity"]) if "quantity" in mapping else ""
    inferred_unit = "股" if "股" in quantity_header else ("手" if "手" in quantity_header else None)
    price_header = header(mapping["price"]) if "price" in mapping else ""
    inferred_raw = "未复权" in price_header
    return {
        "total": len(frame),
        "columns": frame.columns.tolist(),
        "preview": preview,
        "mapping": mapping,
        "missing": missing,
        "inferred_unit": inferred_unit,
        "inferred_raw": inferred_raw,
        "labels": LABELS,
    }


@router.post("/forensics/check", summary="核查外部成交记录")
def forensics_check(req: ForensicsCheckRequest, user: dict = Depends(get_current_user)):
    from quant_platform.forensics.checks import ORDER, check_trades, load_evidence, verdict
    from quant_platform.forensics.parsing import parse_trades, read_material

    try:
        frame = read_material(req.content)
        parsed = parse_trades(frame, req.mapping, req.unit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=_sanitize_detail(exc))

    if not parsed.errors.empty:
        return {
            "status": "errors",
            "errors": parsed.errors.to_dict(orient="records"),
            "verdict": None,
            "findings": [],
            "counts": {},
            "covered": 0,
            "total": len(parsed.trades),
        }

    # 重复记录检测
    duplicates = []
    if parsed.trades.duplicated(["date", "symbol", "side", "quantity", "price"]).any():
        duplicates = parsed.trades[parsed.trades.duplicated(["date", "symbol", "side", "quantity", "price"], keep=False)].index.tolist()

    try:
        from quant_platform.core.config import load_app_config

        config = load_app_config(str(CONFIG_PATH))
        root = Path(str(config["data"]["repository"])).resolve()
        if not root.exists():
            raise FileNotFoundError(f"数据目录不存在：{root}")
        master, bars = load_evidence(root, parsed.trades)
        findings = check_trades(parsed.trades, master, bars, req.basis == "未复权")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"本地数据暂时无法读取，请检查数据目录是否已初始化")

    finding_records = findings.to_dict(orient="records")
    counts = {label: int((findings["结论"] == label).sum()) for label in ORDER}
    covered = len(parsed.trades) - findings[findings["结论"].eq("证据不足")]["表格行"].nunique()
    return {
        "status": "ok",
        "verdict": verdict(findings),
        "findings": finding_records,
        "counts": counts,
        "covered": covered,
        "total": len(parsed.trades),
        "duplicates": duplicates,
        "order": ORDER,
    }


# --------------------------------------------------------------------------- #
# 7. 数据管理
# --------------------------------------------------------------------------- #

@router.get("/data-center/overview", summary="数据中心概览")
def data_overview(user: dict = Depends(get_current_user)):
    service = build_data_center_service(user)
    overview = service.overview()
    market = overview.market.to_dict()
    last_source = ""
    if not overview.manifests.empty:
        daily = overview.manifests[
            overview.manifests["dataset"].eq("daily_bars")
            & overview.manifests["status"].eq("SUCCESS")
        ]
        if not daily.empty:
            last_source = str(daily.iloc[0]["source"])
    per_symbol: list[dict[str, Any]] = []
    if not overview.per_symbol.empty:
        for _, row in overview.per_symbol.iterrows():
            start = row["start_date"]
            end = row["end_date"]
            per_symbol.append({
                "symbol": to_bare(str(row["symbol"])),
                "coverage": round(float(row["coverage_ratio"] or 0.0), 4),
                "start_date": start.isoformat() if start is not None else None,
                "end_date": end.isoformat() if end is not None else None,
                "rows": int(row["rows"] or 0),
            })
    # 数据源就绪状态（含 XTick 首选来源），迁移自 AlphaQuant 1_data_management。
    providers: list[dict[str, Any]] = []
    status_frame = service.market_source_status()
    if not status_frame.empty:
        for _, row in status_frame.iterrows():
            providers.append({
                "provider": str(row["provider"]),
                "display_name": str(row["display_name"]),
                "role": str(row["role"]),
                "readiness": str(row["readiness"]),
                "detail": str(row["detail"]),
            })
    return {
        "security_count": overview.security_count,
        "configured_symbol_count": overview.configured_symbol_count,
        "coverage_ratio": round(float(market["coverage_ratio"]), 4),
        "market_rows": int(market["rows"]),
        "unknown_status_rows": int(market["unknown_status_rows"]),
        "last_market_source": last_source,
        "benchmark_symbol": overview.benchmark_symbol,
        "benchmark_name": service.benchmark_name,
        "benchmarks": dict(BENCHMARKS),
        "providers": providers,
        "per_symbol": per_symbol,
    }


@router.post("/data-center/update", summary="运行数据更新")
def data_update(body: dict[str, Any], user: dict = Depends(get_current_user)):
    try:
        start = date.fromisoformat(str(body.get("start_date") or ""))
    except ValueError:
        start = date.today() - timedelta(days=365)
    try:
        end = date.fromisoformat(str(body.get("end_date") or ""))
    except ValueError:
        end = date.today()
    service = build_data_center_service(user)
    # 基准指数多选：允许按名称或代码指定（迁移自 AlphaQuant）。
    benchmark_symbols: list[str] | None = None
    raw_benchmarks = body.get("benchmark_symbols")
    if isinstance(raw_benchmarks, list) and raw_benchmarks:
        benchmark_symbols = [
            BENCHMARKS.get(str(item), to_canonical(str(item))) for item in raw_benchmarks
        ]
    # 指定行情来源顺序与是否允许回退（迁移自 AlphaQuant）。
    market_source_order: list[str] | None = None
    raw_order = body.get("market_source_order")
    if isinstance(raw_order, list) and raw_order:
        market_source_order = [str(item) for item in raw_order]
    allow_fallback = body.get("allow_market_fallback")
    # 下载为长任务：全局串行执行，且临时切到 backend CWD 以兼容数据源相对路径。
    with DATA_UPDATE_LOCK, _backend_cwd():
        results = service.update_all(
            start,
            end,
            include_security_master=bool(body.get("include_security_master", True)),
            include_market=bool(body.get("include_market", True)),
            include_benchmark=bool(body.get("include_benchmark", True)),
            market_source_order=market_source_order,
            allow_market_fallback=None if allow_fallback is None else bool(allow_fallback),
            benchmark_symbols=benchmark_symbols,
        )
    payload: list[dict[str, Any]] = []
    for result in results:
        payload.append({
            "dataset": result.dataset,
            "version_id": result.version_id,
            "status": result.status,
            "rows": result.rows,
            "message": result.message,
            "error": result.error or "",
            "symbol": getattr(result, "symbol", None) or "",
        })
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO data_manifests (user_id, dataset, source, status, rows, message, completed_at) VALUES (?,?,?,?,?,?,?)",
                (user["id"], result.dataset, "auto", result.status, result.rows, result.message, _now()),
            )
    return {"results": payload}


# --------------------------------------------------------------------------- #
# 7.5 全市场数据任务面板（迁移自 AlphaQuant data_job_panel.py + data_jobs.py）
# --------------------------------------------------------------------------- #


def _data_jobs() -> "DataJobs":
    from quant_platform.application.data_jobs import DataJobs

    return DataJobs(RUNTIME_ROOT / "data_jobs", CONFIG_PATH, cwd=BACKEND_ROOT)


_DATA_JOB_STATUS_LABELS = {
    "STARTING": "启动中",
    "RUNNING": "运行中",
    "RETRYING": "等待重试",
    "SUCCESS": "完成",
    "PARTIAL": "部分失败",
    "FAILED": "失败",
    "STOPPED": "已停止",
    "INTERRUPTED": "意外中断",
}


@router.get("/data-center/jobs", summary="全市场回填任务列表与进度")
def data_jobs_list(user: dict = Depends(get_current_user)):
    records = _data_jobs().records()
    for record in records:
        record["status_label"] = _DATA_JOB_STATUS_LABELS.get(record.get("status", ""), record.get("status", ""))
    return {"records": records}


@router.post("/data-center/jobs/start", status_code=status.HTTP_201_CREATED, summary="启动全市场回填任务")
def data_jobs_start(body: dict[str, Any], user: dict = Depends(get_current_user)):
    try:
        start = date.fromisoformat(str(body.get("start_date") or ""))
        end = date.fromisoformat(str(body.get("end_date") or ""))
    except ValueError:
        raise HTTPException(status_code=422, detail="请提供有效的开始/结束日期")
    datasets = body.get("datasets") or ["bars", "actions", "derived"]
    try:
        job = _data_jobs().start(start, end, datasets)
    except (ValueError, RuntimeError, OSError) as exc:
        raise HTTPException(status_code=409, detail=_sanitize_detail(exc))
    job["status_label"] = _DATA_JOB_STATUS_LABELS.get(job.get("status", ""), job.get("status", ""))
    return job


@router.post("/data-center/jobs/{job_id}/stop", summary="停止全市场回填任务")
def data_jobs_stop(job_id: str, user: dict = Depends(get_current_user)):
    try:
        _data_jobs().stop(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=_sanitize_detail(exc))
    return {"stopped": job_id}


@router.get("/data-center/jobs/{job_id}/log", summary="全市场回填任务日志（最近 32KB，已脱敏）")
def data_jobs_log(job_id: str, user: dict = Depends(get_current_user)):
    from quant_platform.core.diagnostics import redact_text

    return {"log": redact_text(_data_jobs().log(job_id))}


@router.get("/data-center/closed-loop", summary="全市场数据闭环落地状态（只读，不访问外网）")
def data_closed_loop_status(user: dict = Depends(get_current_user)):
    service = build_data_center_service(user)
    try:
        return service.closed_loop_status()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"读取闭环状态失败：{_sanitize_detail(exc)}")


# --------------------------------------------------------------------------- #
# 8. XTick 数据服务（真实接口，迁移自 AlphaQuant 11_xtick_data.py）
# --------------------------------------------------------------------------- #

_XTICK_CATALOG_URL = "http://www.xtick.top/assets/apidoc.json"
_XTICK_CATALOG_FILE = Path(__file__).resolve().parents[2] / "quant_platform" / "web" / "assets" / "xtick_apidoc.json"
_XTICK_DEFAULT_BASE_URL = "http://api.xtick.top"
# 官方文档里个别参数名缺失/有误：/doc/hot/bidhistory 的第二个参数名在文档里为空，
# 实测真实参数名是 seq（0=开盘数据，1=集合竞价最后一条数据）。
_XTICK_PARAM_NAME_PATCH = {"": "seq"}
_XTICK_DATE_PARAM_HINTS = ("startdate", "enddate", "tradedate")
_XTICK_TAB_NAMES = {1: "行情数据", 2: "盯盘数据", 3: "核心数据", 4: "短线热点", 8: "量化因子", 9: "金融指标"}
_XTICK_LABELS = {
    "type": "标的类型", "code": "代码", "fq": "复权", "period": "周期",
    "startDate": "开始日期", "endDate": "结束日期", "tradeDate": "交易日期",
    "token": "Token", "symbol": "市场", "field": "字段", "minutes": "最近N分钟",
    "seq": "序号", "option": "选项",
}


def _xtick_credentials() -> DataCredentialStore:
    return DataCredentialStore(RUNTIME_ROOT / "data_source_settings.json")


def _xtick_resolve() -> tuple[str, str]:
    """返回 (token, base_url)：本地凭证优先，环境变量兜底。"""

    store = _xtick_credentials()
    token = store.resolve("xtick", "token", "XTICK_TOKEN")
    base_url = store.get("xtick").get("base_url", "") or _XTICK_DEFAULT_BASE_URL
    return token, base_url


def _xtick_load_catalog() -> list[dict[str, Any]]:
    """加载官方接口文档；本地有缓存文件则直接读，否则在线拉取并缓存。"""

    if _XTICK_CATALOG_FILE.exists():
        return json.loads(_XTICK_CATALOG_FILE.read_text(encoding="utf-8"))
    import requests

    response = requests.get(_XTICK_CATALOG_URL, timeout=30)
    response.raise_for_status()
    catalog = response.json()
    try:
        _XTICK_CATALOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        _XTICK_CATALOG_FILE.write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError:
        pass
    return catalog


def _xtick_parse_range(range_str: str | None) -> list[tuple[str, str]]:
    """把官方文档的枚举串（"1-沪深京A股，2-沪深指数"）解析成 [(值, 含义), ...]。"""

    options: list[tuple[str, str]] = []
    for item in re.split(r"[，,]", range_str or ""):
        item = item.strip()
        if not item:
            continue
        if "-" in item:
            value, _, label = item.partition("-")
            options.append((value.strip(), label.strip()))
        else:
            options.append((item, item))
    return options


def _xtick_demo_defaults(demo_url: str | None) -> dict[str, str]:
    if not demo_url:
        return {}
    from urllib.parse import parse_qsl, urlparse

    return dict(parse_qsl(urlparse(demo_url).query, keep_blank_values=True))


def _xtick_input_type(name: str, param: dict[str, Any]) -> str:
    if param.get("range"):
        return "select"
    kind = str(param.get("type", "String")).lower()
    if kind in ("int", "long", "double", "float", "bigdecimal"):
        return "number"
    if name.lower() in _XTICK_DATE_PARAM_HINTS:
        return "date"
    return "text"


def _xtick_catalog_payload() -> list[dict[str, Any]]:
    """把官方 apidoc 转成前端可渲染的目录结构（含枚举选项与默认值）。"""

    catalog = _xtick_load_catalog()
    payload: list[dict[str, Any]] = []
    for category in catalog:
        apis: list[dict[str, Any]] = []
        for api in category.get("docApis", []):
            demo = _xtick_demo_defaults(api.get("demo"))
            inputs: list[dict[str, Any]] = []
            for raw in api.get("inputParas", []):
                name = _XTICK_PARAM_NAME_PATCH.get(raw.get("name") or "", raw.get("name") or "")
                if name == "token":
                    continue
                options = _xtick_parse_range(raw.get("range"))
                inputs.append({
                    "name": name,
                    "label": _XTICK_LABELS.get(name, name),
                    "type": _xtick_input_type(name, raw),
                    "default": demo.get(name, ""),
                    "range": raw.get("range") or "",
                    "options": [{"value": value, "label": label} for value, label in options],
                })
            apis.append({
                "id": api.get("id"),
                "name": api.get("name", ""),
                "url": api.get("url", ""),
                "description": api.get("description", ""),
                "inputs": inputs,
                "outputs": [
                    {"name": para.get("name"), "description": para.get("description", "")}
                    for para in api.get("outputParas") or []
                    if para.get("name")
                ],
            })
        payload.append({
            "id": category.get("id"),
            "name": _XTICK_TAB_NAMES.get(category.get("id"), category.get("name", "")),
            "apis": apis,
        })
    return payload


def _xtick_request_api(base_url: str, path: str, token: str, params: dict[str, str]) -> Any:
    """请求一个 XTick 数据接口并返回解析后的数据。

    兼容两种响应：成功为 ZIP 压缩包（内含 data.json）；失败为普通 JSON。
    """

    import io
    import zipfile

    import requests

    response = requests.get(
        f"{base_url.rstrip('/')}{path}",
        params={"token": token, **params},
        timeout=30,
    )
    response.raise_for_status()
    content = response.content
    if content[:2] == b"PK":  # zip 魔数
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return json.loads(archive.read("data.json"))
    payload = json.loads(content.decode("utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("code"), int):
        code = payload["code"]
        if code not in (0, 200):
            raise RuntimeError(f"XTick 接口返回错误 [{code}]：{payload.get('message', '未知错误')}")
        if "data" in payload:
            return payload["data"]
    return payload


def _xtick_to_rows(result: Any) -> tuple[list[dict[str, Any]], bool]:
    """把返回数据转成行列表；不支持的返回原始 JSON（is_json=True）。"""

    frame: pd.DataFrame | None = None
    if isinstance(result, list):
        frame = pd.json_normalize(result) if result else pd.DataFrame()
    elif isinstance(result, dict):
        inner = result.get("data")
        if isinstance(inner, dict) and inner and all(isinstance(v, list) for v in inner.values()):
            frame = pd.DataFrame(inner)
        elif result and all(isinstance(v, list) for v in result.values()):
            frame = pd.DataFrame(result)
        elif result and all(not isinstance(v, (dict, list)) for v in result.values()):
            frame = pd.DataFrame([result])
    if frame is None:
        return [{"value": result}] if not isinstance(result, (dict, list)) else [], True
    return json.loads(frame.to_json(orient="records", force_ascii=False)), False


@router.get("/xtick/catalog", summary="XTick 接口目录（官方 apidoc 动态生成）")
def xtick_catalog(user: dict = Depends(get_current_user)):
    try:
        return {"catalog": _xtick_catalog_payload()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"加载 XTick 接口文档失败：{_sanitize_detail(exc)}")


@router.get("/xtick/status", summary="XTick 凭证状态")
def xtick_status(user: dict = Depends(get_current_user)):
    token, base_url = _xtick_resolve()
    return {
        "configured": bool(token),
        "base_url": base_url,
        "message": "XTick 凭证已配置" if token else "尚未配置 XTick Token，请先在下方保存凭证（或设置环境变量 XTICK_TOKEN）",
    }


@router.post("/xtick/credentials", summary="保存 XTick 凭证")
def xtick_credentials_save(body: dict[str, Any], user: dict = Depends(get_current_user)):
    token = str(body.get("token", "")).strip()
    base_url = str(body.get("base_url", "")).strip() or _XTICK_DEFAULT_BASE_URL
    if not token:
        raise HTTPException(status_code=422, detail="Token 不能为空")
    _xtick_credentials().save("xtick", token=token, base_url=base_url)
    return {"ok": True, "message": "XTick 凭证已保存"}


@router.post("/xtick/request", summary="请求 XTick 接口（真实调用，自动解包 ZIP 响应）")
def xtick_request(body: dict[str, Any], user: dict = Depends(get_current_user)):
    token, base_url = _xtick_resolve()
    if not token:
        raise HTTPException(status_code=428, detail="尚未配置 XTick Token，请先保存凭证或设置环境变量 XTICK_TOKEN")
    url = str(body.get("url") or "")
    if not url:
        raise HTTPException(status_code=422, detail="缺少接口路径 url")
    params = {str(k): str(v) for k, v in (body.get("params") or {}).items() if str(v) != ""}
    request_type = str(params.get("type", ""))
    try:
        result = _xtick_request_api(base_url, url, token, params)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=_sanitize_detail(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"XTick 请求失败：{_sanitize_detail(exc)}")
    rows, is_json = _xtick_to_rows(result)
    if not is_json and rows:
        # 统一股票名称展示（迁移自 AlphaQuant security_names.xtick_security_names）。
        try:
            frame = pd.DataFrame(rows)
            if request_type in ("", "1", "2"):
                frame = xtick_security_names(frame, request_type or None)
            # 按官方文档 outputParas 重命名列：原字段名 -> 中文描述（原字段名）。
            rename: dict[str, str] = {}
            for para in body.get("outputs") or []:
                name, desc = para.get("name"), para.get("description")
                if not name or not desc:
                    continue
                desc = desc.splitlines()[0].strip()
                if desc and desc != name and name in frame.columns:
                    rename[name] = f"{desc}（{name}）"
            frame = frame.rename(columns=rename)
            rows = json.loads(frame.to_json(orient="records", force_ascii=False))
        except Exception:  # noqa: BLE001 - 名称增强失败不影响原始数据返回
            pass
    return {"rows": rows, "count": len(rows), "is_json": is_json}


# --------------------------------------------------------------------------- #
# 9. 风险管理
# --------------------------------------------------------------------------- #

_DEFAULT_RISK = {"enabled": True, "max_total_weight": 0.95, "max_single_weight": 0.20, "max_positions": 20,
                 "minimum_cash_ratio": 0.05, "max_drawdown": 0.25, "daily_position_limits": True,
                 "drawdown_action": "reduce", "drawdown_target_weight": 0.50}


@router.get("/risk", summary="风控配置")
def risk_get(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM risk_limits WHERE user_id = ?", (user["id"],)).fetchone()
    if not row:
        return dict(_DEFAULT_RISK)
    return {"enabled": bool(row["enabled"]), "max_total_weight": row["max_total_weight"],
            "max_single_weight": row["max_single_weight"], "max_positions": row["max_positions"],
            "minimum_cash_ratio": row["minimum_cash_ratio"], "max_drawdown": row["max_drawdown"],
            "daily_position_limits": bool(row["daily_position_limits"]), "drawdown_action": row["drawdown_action"],
            "drawdown_target_weight": row["drawdown_target_weight"]}


@router.put("/risk", summary="保存风控配置")
def risk_save(body: dict[str, Any], user: dict = Depends(get_current_user)):
    merged = {**_DEFAULT_RISK, **body}
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO risk_limits (user_id, enabled, max_total_weight, max_single_weight, max_positions, minimum_cash_ratio, max_drawdown, daily_position_limits, drawdown_action, drawdown_target_weight, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled, max_total_weight=excluded.max_total_weight, max_single_weight=excluded.max_single_weight, max_positions=excluded.max_positions, minimum_cash_ratio=excluded.minimum_cash_ratio, max_drawdown=excluded.max_drawdown, daily_position_limits=excluded.daily_position_limits, drawdown_action=excluded.drawdown_action, drawdown_target_weight=excluded.drawdown_target_weight, updated_at=excluded.updated_at",
            (user["id"], 1 if merged["enabled"] else 0, merged["max_total_weight"], merged["max_single_weight"],
             merged["max_positions"], merged["minimum_cash_ratio"], merged["max_drawdown"],
             1 if merged["daily_position_limits"] else 0, merged["drawdown_action"], merged["drawdown_target_weight"], _now()),
        )
    return {"saved": True}


@router.get("/risk/events", summary="最近风控记录（模拟）")
def risk_events(user: dict = Depends(get_current_user)):
    rng = random.Random(abs(hash(user["id"])))
    events = []
    for i in range(40):
        decision = rng.choice(["REJECT", "ADJUST", "PASS"])
        events.append({"run_id": f"run-{rng.randint(1, 9)}", "trade_date": (date.today() - timedelta(days=i)).isoformat(),
                       "symbol": f"{600000 + rng.randint(0, 500)}", "decision": decision,
                       "reason": "超过单股最大权重" if decision != "PASS" else ""})
    return {"events": events, "checks": len(events), "adjustments": sum(1 for e in events if e["decision"] == "ADJUST"),
            "rejections": sum(1 for e in events if e["decision"] == "REJECT")}


# --------------------------------------------------------------------------- #
# 10. 股票池管理
#    （模拟交易入口已移除，迁移自 AlphaQuant 092b2b6 导航调整）
# --------------------------------------------------------------------------- #

_DEFAULT_UNIVERSE = ["600519", "000001", "300750", "601318", "000858"]


def _local_symbol_stats() -> dict[str, dict[str, Any]]:
    """本地 daily_bars 的 symbol -> {local_rows, start_date, end_date} 统计。"""

    bars = market_repository().read_table("daily_bars")
    stats: dict[str, dict[str, Any]] = {}
    if bars.empty:
        return stats
    frame = pd.DataFrame(
        {"symbol": bars["symbol"].astype(str), "d": pd.to_datetime(bars["trade_date"], errors="coerce")}
    ).dropna(subset=["d"])
    if frame.empty:
        return stats
    grouped = frame.groupby("symbol")["d"].agg(["size", "min", "max"])
    for symbol, row in grouped.iterrows():
        stats[symbol] = {
            "local_rows": int(row["size"]),
            "start_date": row["min"].date().isoformat(),
            "end_date": row["max"].date().isoformat(),
        }
    return stats


@router.get("/universe", summary="股票池设置")
def universe_get(user: dict = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM universe WHERE user_id = ?", (user["id"],)).fetchone()
    if not row:
        symbols = list(_DEFAULT_UNIVERSE)
        filters = {"exclude_st": True, "exclude_suspended": True, "minimum_listing_days": 60,
                   "minimum_history_days": 120, "minimum_average_amount": 0}
    else:
        symbols = json.loads(row["symbols"])
        filters = {"exclude_st": bool(row["exclude_st"]), "exclude_suspended": bool(row["exclude_suspended"]),
                   "minimum_listing_days": row["minimum_listing_days"], "minimum_history_days": row["minimum_history_days"],
                   "minimum_average_amount": row["minimum_average_amount"]}
    names = security_names()
    stats = _local_symbol_stats()
    description = []
    for symbol in symbols:
        canonical = to_canonical(symbol)
        stat = stats.get(canonical, {})
        description.append({
            "symbol": symbol,
            "name": names.get(canonical, "未知"),
            "local_rows": stat.get("local_rows", 0),
            "start_date": stat.get("start_date", "—"),
            "end_date": stat.get("end_date", "—"),
        })
    return {"symbols": symbols, "filters": filters, "description": description}


class UniverseAddIn(BaseModel):
    symbols: list[str]


class UniverseRemoveIn(BaseModel):
    symbols: list[str]


def _load_universe_symbols(user_id: int) -> list[str]:
    with get_conn() as conn:
        row = conn.execute("SELECT symbols FROM universe WHERE user_id = ?", (user_id,)).fetchone()
    return json.loads(row["symbols"]) if row else list(_DEFAULT_UNIVERSE)


def _save_universe(user_id: int, symbols: list[str], filters: dict[str, Any] | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO universe (user_id, symbols, exclude_st, exclude_suspended, minimum_listing_days, minimum_history_days, minimum_average_amount, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET symbols=excluded.symbols, updated_at=excluded.updated_at",
            (user_id, json.dumps(symbols, ensure_ascii=False), 1, 1, 60, 120, 0, _now()),
        )


@router.post("/universe/add", summary="添加股票")
def universe_add(body: UniverseAddIn, user: dict = Depends(get_current_user)):
    current = _load_universe_symbols(user["id"])
    for s in body.symbols:
        norm = s.split(".")[0].strip()
        if re.fullmatch(r"\d{6}", norm) and norm not in current:
            current.append(norm)
    _save_universe(user["id"], current)
    return {"symbols": current, "count": len(current)}


@router.post("/universe/remove", summary="移除股票")
def universe_remove(body: UniverseRemoveIn, user: dict = Depends(get_current_user)):
    current = _load_universe_symbols(user["id"])
    remove = {s.split(".")[0].strip() for s in body.symbols}
    current = [s for s in current if s not in remove]
    _save_universe(user["id"], current)
    return {"symbols": current, "count": len(current)}


@router.get("/universe/search", summary="按名称搜索证券主表")
def universe_search(q: str = "", user: dict = Depends(get_current_user)):
    query = q.strip()
    if not query:
        return {"results": []}
    master = market_repository().read_table("security_master")
    if master.empty or "name" not in master.columns:
        return {"results": []}
    names = master["name"].astype(str)
    symbols = master["symbol"].astype(str)
    matched = master[names.str.contains(query, case=False, na=False, regex=False)]
    if query.isdigit():
        by_code = master[symbols.str.startswith(query)]
        matched = pd.concat([matched, by_code]).drop_duplicates("symbol")
    results = [
        {"symbol": to_bare(str(symbol)), "name": str(name)}
        for symbol, name in zip(
            matched["symbol"].head(20), matched["name"].head(20), strict=False
        )
    ]
    return {"results": results}


@router.put("/universe/filters", summary="保存股票过滤设置")
def universe_filters(body: dict[str, Any], user: dict = Depends(get_current_user)):
    symbols = _load_universe_symbols(user["id"])
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO universe (user_id, symbols, exclude_st, exclude_suspended, minimum_listing_days, minimum_history_days, minimum_average_amount, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET exclude_st=excluded.exclude_st, exclude_suspended=excluded.excluded.exclude_suspended, minimum_listing_days=excluded.minimum_listing_days, minimum_history_days=excluded.minimum_history_days, minimum_average_amount=excluded.minimum_average_amount, updated_at=excluded.updated_at",
            (user["id"], json.dumps(symbols, ensure_ascii=False), 1 if body.get("exclude_st", True) else 0,
             1 if body.get("exclude_suspended", True) else 0, body.get("minimum_listing_days", 60),
             body.get("minimum_history_days", 120), body.get("minimum_average_amount", 0), _now()),
        )
    return {"saved": True}


# --------------------------------------------------------------------------- #
# 11. Jev 结构化决策中心
# --------------------------------------------------------------------------- #

class JevDecideIn(BaseModel):
    type: str = Field(..., pattern="^(choice|noul|score)$")
    question: str = ""
    condition: str = ""
    options: list[str] = Field(default_factory=list)
    levels: list[str] = Field(default_factory=list)
    state: dict[str, Any] | list[Any] | str | None = Field(default_factory=dict)


def _service_url(value: str) -> str:
    from urllib.parse import urlsplit
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise HTTPException(status_code=422, detail="请填写有效的 HTTP/HTTPS 服务地址")
    return value


def _integration_call(action):
    try:
        return action()
    except Exception:
        raise HTTPException(status_code=502, detail="服务调用失败，请检查服务地址、API Key、权限及网络连接") from None


def _jev_client(user_id: int) -> JevClient:
    resolved = _llm_store(user_id).resolve("openrouter")
    url = resolved["base_url"].rstrip("/")
    if not url.endswith("/decisions"):
        if url.endswith("/api/v1"):
            url = url[:-len("/api/v1")] + "/api/alpha/decisions"
        else:
            url += "/api/alpha/decisions"
    return JevClient(api_key=resolved["api_key"] or None, base_url=url, model=resolved["model"])


@router.get("/jev/settings", summary="Jev 配置状态")
def jev_settings(user: dict = Depends(get_current_user)):
    client = _jev_client(user["id"])
    return {"configured": client.has_key, "base_url": client.base_url, "model": client.model}


class JevSettingsIn(BaseModel):
    base_url: str = "https://openrouter.ai/api/alpha/decisions"
    api_key: str = ""
    model: str = "typesafe/jev-1.13"


@router.post("/jev/settings", summary="保存当前账户 Jev 配置")
def jev_settings_save(body: JevSettingsIn, user: dict = Depends(get_current_user)):
    store = _llm_store(user["id"])
    key = body.api_key.strip() or store.get("openrouter")["api_key"]
    if not body.model.strip():
        raise HTTPException(status_code=422, detail="请填写模型名称")
    store.save("openrouter", base_url=_service_url(body.base_url), api_key=key, model=body.model.strip())
    return {"ok": True}


@router.post("/jev/decide", summary="Jev 结构化决策（Choice / Noul / Score）")
def jev_decide(body: JevDecideIn, user: dict = Depends(get_current_user)):
    body.options = [item.strip() for item in body.options]
    body.levels = [item.strip() for item in body.levels]
    client = _jev_client(user["id"])
    try:
        if body.type == "choice":
            if not body.question.strip() or len(body.options) < 2 or any(not x.strip() for x in body.options) or len(set(body.options)) != len(body.options):
                raise HTTPException(status_code=422, detail="请填写问题和至少两个不同的非空选项")
            req = ChoiceRequest(question=body.question, options=body.options, state=body.state)
            resp = _integration_call(lambda: client.choice(req))
        elif body.type == "noul":
            if not body.condition.strip():
                raise HTTPException(status_code=422, detail="Noul 决策需要提供 condition 条件描述")
            req = NoulRequest(condition=body.condition, state=body.state)
            resp = _integration_call(lambda: client.noul(req))
        else:
            if not body.question.strip() or len(body.levels) < 2 or any(not x.strip() for x in body.levels) or len(set(body.levels)) != len(body.levels):
                raise HTTPException(status_code=422, detail="请填写问题和至少两个不同的非空等级")
            req = ScoreRequest(question=body.question, levels=body.levels, state=body.state)
            resp = _integration_call(lambda: client.score(req))
        return resp.__dict__
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=_sanitize_detail(exc))


# --------------------------------------------------------------------------- #
# 12. WeKnora 知识库问答
# --------------------------------------------------------------------------- #

def _weknora_credentials(user_id: int) -> DataCredentialStore:
    return DataCredentialStore(_llm_store(user_id).path.parent / "weknora_settings.json")


def _weknora_resolve(user_id: int) -> tuple[str, str]:
    """返回 (base_url, api_key)：本地凭证优先，环境变量兜底。"""
    store = _weknora_credentials(user_id)
    base_url = store.resolve("weknora", "base_url", "WEKNORA_BASE_URL")
    api_key = store.resolve("weknora", "api_key", "WEKNORA_API_KEY")
    return base_url, api_key


def _weknora_client(user_id: int) -> WeKnoraClient:
    base_url, api_key = _weknora_resolve(user_id)
    return WeKnoraClient(base_url=base_url or None, api_key=api_key or None)


@router.get("/weknora/settings", summary="WeKnora 配置状态")
def weknora_settings(user: dict = Depends(get_current_user)):
    base_url, api_key = _weknora_resolve(user["id"])
    return {
        "configured": bool(base_url),
        "base_url": base_url,
        "api_key_configured": bool(api_key),
        "message": "WeKnora 服务已配置" if base_url else "尚未配置 WeKnora 服务地址，请在下方保存配置（或设置环境变量 WEKNORA_BASE_URL）",
    }


class WeKnoraSettingsIn(BaseModel):
    base_url: str = ""
    api_key: str = ""


@router.post("/weknora/settings", summary="保存 WeKnora 配置")
def weknora_settings_save(body: WeKnoraSettingsIn, user: dict = Depends(get_current_user)):
    base_url = _service_url(body.base_url)
    store = _weknora_credentials(user["id"])
    api_key = body.api_key.strip() or store.get("weknora").get("api_key", "")
    if not base_url:
        raise HTTPException(status_code=422, detail="WeKnora 服务地址不能为空")
    store.save("weknora", base_url=base_url, api_key=api_key)
    return {"ok": True, "message": "WeKnora 配置已保存"}


@router.get("/weknora/knowledge-bases", summary="WeKnora 知识库列表")
def weknora_list_bases(user: dict = Depends(get_current_user)):
    client = _weknora_client(user["id"])
    return {"items": _integration_call(client.list_knowledge_bases), "configured": client.configured, "mock": not client.configured}


class WeKnoraChatIn(BaseModel):
    question: str = Field(..., min_length=1)
    knowledge_base_id: str | None = None


@router.post("/weknora/chat", summary="WeKnora 知识库问答")
def weknora_chat(body: WeKnoraChatIn, user: dict = Depends(get_current_user)):
    client = _weknora_client(user["id"])
    if not body.question.strip() or (client.configured and not body.knowledge_base_id):
        raise HTTPException(status_code=422, detail="请填写问题并选择知识库")
    return _integration_call(lambda: client.chat(body.question.strip(), body.knowledge_base_id))


class WeKnoraQueryIn(BaseModel):
    query: str = Field(..., min_length=1)
    knowledge_base_id: str | None = None
    top_k: int = Field(5, ge=1, le=20)


@router.post("/weknora/query", summary="WeKnora 文档检索")
def weknora_query(body: WeKnoraQueryIn, user: dict = Depends(get_current_user)):
    client = _weknora_client(user["id"])
    if not body.query.strip() or (client.configured and not body.knowledge_base_id):
        raise HTTPException(status_code=422, detail="请填写检索词并选择知识库")
    return {"items": _integration_call(lambda: client.query(body.query.strip(), body.knowledge_base_id, body.top_k)), "mock": not client.configured}
