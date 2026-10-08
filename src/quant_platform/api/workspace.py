"""Model settings, risk rules, Python strategies and custom factor management."""

import platform
import shutil
import sys
from dataclasses import asdict
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import pandas as pd
import yaml
from fastapi import APIRouter, Depends, Query, Response

from quant_platform.agents_bridge.data_credentials import DataCredentialStore
from quant_platform.agents_bridge.llm_settings import PROVIDER_CATALOG, LLMSettingsStore
from quant_platform.agents_bridge.proxy_settings import ProxySettingsStore
from quant_platform.agents_bridge.sources import NEWS_SOURCES, STOCK_SOURCES
from quant_platform.api.common import ApiError, csv_response, safe_wire, table, wire
from quant_platform.api.dependencies import ApiContext, context
from quant_platform.api.schemas import RiskInput
from quant_platform.api.workspace_schemas import (
    CredentialInput,
    CustomFactorInput,
    ModelSettingsInput,
    ProxyInput,
    PythonInput,
)
from quant_platform.core.config import load_yaml
from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.custom import (
    FIELDS,
    OPERATORS,
    build_custom_factor,
    custom_factor_to_dict,
    load_custom_factors,
    save_custom_factors,
)
from quant_platform.factors.registry import FactorRegistry
from quant_platform.factors.taxonomy import INTENT_TERMS, classify_factor
from quant_platform.risk.config import RiskLimits
from quant_platform.strategies.rule_schema import INDICATOR_LABELS, OPERATOR_LABELS
from quant_platform.user_strategies.loader import UserStrategyLoader
from quant_platform.user_strategies.safety import check_strategy_source
from quant_platform.user_strategies.starter import STARTER_STRATEGY_CODE
from quant_platform.user_strategies.store import UserStrategyStore

router = APIRouter(tags=["workspace"])
Context = Annotated[ApiContext, Depends(context)]


def settings_store(ctx):
    return LLMSettingsStore(ctx.runtime_root / "llm_settings.json")


def credential_store(ctx):
    return DataCredentialStore(ctx.runtime_root / "data_source_settings.json")


def factor_registry(ctx):
    from quant_platform.factors.alpha101 import alpha101_factors
    from quant_platform.factors.builtins import builtin_factors

    registry = FactorRegistry()
    for factor in [
        *builtin_factors(),
        *alpha101_factors(),
        *load_custom_factors(ctx.runtime_root / "custom_factors.json"),
    ]:
        registry.register(factor)
    return registry


def factor_metadata(factor):
    return wire({key: getattr(factor, key) for key in FactorDefinition.__dataclass_fields__})


def model_snapshot(ctx, provider=None):
    store = settings_store(ctx)
    provider = provider or store.get_default_provider()
    if provider not in PROVIDER_CATALOG:
        raise ApiError(422, "unknown_provider", "模型提供方不存在")
    resolved = store.resolve(provider)
    if PROVIDER_CATALOG[provider].requires_key and not resolved["api_key"]:
        raise ApiError(409, "model_not_ready", "请先配置模型凭证")
    if provider == "custom" and not resolved["base_url"]:
        raise ApiError(409, "model_not_ready", "自定义模型需要接口地址")
    return {"provider": provider, "resolved": resolved}


@router.get("/settings")
def settings(ctx: Context):
    store, credentials = settings_store(ctx), credential_store(ctx)
    return {
        "default_provider": store.get_default_provider(),
        "providers": [
            {
                **asdict(spec),
                "base_url": store.resolve(key)["base_url"],
                "model": store.resolve(key)["model"],
                "key_configured": bool(store.resolve(key)["api_key"]),
            }
            for key, spec in PROVIDER_CATALOG.items()
        ],
        "data_sources": {
            name: {
                "configured": {
                    field: bool(credentials.resolve(name, field, env))
                    for field, env in {
                        "xtick": {"token": "XTICK_TOKEN"},
                        "ifind": {"username": "IFIND_USERNAME", "password": "IFIND_PASSWORD"},
                        "tushare": {"token": "TUSHARE_TOKEN"},
                    }[name].items()
                },
                "base_url": credentials.get(name).get("base_url", ""),
            }
            for name in ("xtick", "ifind", "tushare")
        },
        "proxy": ProxySettingsStore(ctx.runtime_root / "proxy_settings.json").load(),
        "stock_sources": STOCK_SOURCES,
        "news_sources": NEWS_SOURCES,
    }


@router.post("/settings/models/{provider}")
def save_model(provider: str, body: ModelSettingsInput, ctx: Context):
    if provider not in PROVIDER_CATALOG:
        raise ApiError(404, "unknown_provider", "模型提供方不存在")
    with ctx.mutation():
        store = settings_store(ctx)
        store.save(
            provider,
            base_url=body.base_url,
            model=body.model,
            api_key=body.api_key if body.api_key is not None else store.get(provider)["api_key"],
        )
        if body.set_default:
            store.save_default_provider(provider)
    return {"saved": True, "default_provider": store.get_default_provider()}


@router.post("/settings/data/{provider}")
def save_credentials(provider: str, body: CredentialInput, ctx: Context):
    allowed = {
        "xtick": {"token", "base_url"},
        "ifind": {"username", "password"},
        "tushare": {"token"},
    }
    if provider not in allowed:
        raise ApiError(404, "unknown_provider", "数据来源不存在")
    values = body.model_dump(exclude_none=True)
    if set(values) - allowed[provider]:
        raise ApiError(422, "invalid_credential_field", "该来源不支持这些凭证字段")
    with ctx.mutation():
        store = credential_store(ctx)
        store.save(provider, **{**store.get(provider), **values})
    return {"saved": True}


@router.post("/settings/proxy")
def save_proxy(body: ProxyInput, ctx: Context):
    with ctx.mutation():
        ProxySettingsStore(ctx.runtime_root / "proxy_settings.json").save(
            body.enabled, body.address
        )
    return {"saved": True}


@router.get("/settings/system")
def system(ctx: Context):
    usage = shutil.disk_usage(ctx.runtime_root.parent)
    return {
        "version": version("quant-platform"),
        "python": sys.version.split()[0],
        "system": platform.platform(),
        "fastapi": version("fastapi"),
        "frontend": "React / TypeScript / Vite",
        "disk_free_bytes": usage.free,
        "runtime": str(ctx.runtime_root),
        "repository": str(ctx.data().repository.root),
        "config": str(ctx.config_path),
        "authentication": "local_only",
    }


@router.get("/risk")
def risk(ctx: Context):
    return wire(ctx.backtests().default_request().risk_limits)


@router.post("/risk")
def save_risk(body: RiskInput, ctx: Context):
    limits = RiskLimits.from_mapping(body.model_dump())
    with ctx.mutation():
        config = load_yaml(ctx.config_path)
        reference = config.get("risk", {}).get("config")
        if reference:
            path = Path(reference).resolve()
            value = {"risk": limits.to_dict()}
        else:
            path, value = ctx.config_path, config
            value["risk"] = limits.to_dict()
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
        temp.replace(path)
    return limits.to_dict()


def risk_event_frame(ctx):
    frames = []
    for record in ctx.backtests().run_store.list_records(successful_only=True)[:10]:
        path = record.path / "risk_events.parquet"
        if path.is_file():
            frame = pd.read_parquet(path)
            frame.insert(0, "run_id", record.run_id)
            frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=["run_id", "trade_date", "decision"])
    return pd.concat(frames, ignore_index=True).sort_values(
        "trade_date",
        ascending=False,
        key=lambda values: pd.to_datetime(values, errors="coerce", utc=True),
    )


@router.get("/risk/events")
def risk_events(ctx: Context, offset: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=5000)):
    frame = risk_event_frame(ctx)
    return {
        **table(frame, offset, limit),
        "counts": {
            "最近检查次数": len(frame),
            "自动调整次数": int(frame.decision.eq("ADJUST").sum()),
            "拒绝次数": int(frame.decision.eq("REJECT").sum()),
        },
    }


@router.get("/risk/events/export.csv")
def export_risk_events(ctx: Context):
    return csv_response(risk_event_frame(ctx), "recent_risk_events.csv")


@router.get("/strategies/python")
def python_strategies(ctx: Context):
    store = UserStrategyStore(ctx.backtests().user_strategy_root)
    return {
        "items": [{**item.to_dict(), "code": item.read_code()} for item in store.list()],
        "starter": STARTER_STRATEGY_CODE,
        "load_errors": safe_wire(ctx.backtests().user_strategy_errors),
    }


@router.post("/strategies/python/check")
def check_python(body: PythonInput):
    return wire(check_strategy_source(body.code))


@router.post("/strategies/python", status_code=201)
def save_python(body: PythonInput, ctx: Context):
    report = check_strategy_source(body.code)
    if report.blocked or (report.warnings and not body.risk_acknowledged):
        raise ApiError(409, "strategy_safety", "请修复阻断项并确认风险提示", wire(report))
    with ctx.mutation():
        result = UserStrategyLoader().load_source(body.code)
        if result.errors or not result.strategies:
            raise ApiError(422, "strategy_invalid", "策略未通过加载检查", safe_wire(result.errors))
        plugin, cls = next(iter(result.strategies.items()))
        record = UserStrategyStore(ctx.backtests().user_strategy_root).save(
            body.code,
            plugin_name=plugin,
            display_name=body.display_name or cls.display_name,
            description=body.description or cls.description,
            source=body.source,
        )
    return {**record.to_dict(), "registered_count": len(result.strategies)}


@router.delete("/strategies/python/{plugin}", status_code=204)
def delete_python(plugin: str, ctx: Context):
    with ctx.mutation():
        store = UserStrategyStore(ctx.backtests().user_strategy_root)
        if plugin not in {r.plugin_name for r in store.list()}:
            raise ApiError(404, "strategy_missing", "自定义策略不存在")
        store.delete(plugin)
    return Response(status_code=204)


@router.get("/factors/editor")
def factor_editor(ctx: Context):
    return {
        "fields": FIELDS,
        "operators": OPERATORS,
        "intents": INTENT_TERMS,
        "indicators": INDICATOR_LABELS,
        "comparisons": OPERATOR_LABELS,
        "items": [
            custom_factor_to_dict(f)
            for f in load_custom_factors(ctx.runtime_root / "custom_factors.json")
        ],
    }


@router.post("/factors/custom", status_code=201)
def save_factor(body: CustomFactorInput, ctx: Context):
    with ctx.mutation():
        if body.name in factor_registry(ctx):
            raise ApiError(409, "factor_exists", "因子标识已存在")
        factor = build_custom_factor(**body.model_dump())
        path = ctx.runtime_root / "custom_factors.json"
        save_custom_factors([*load_custom_factors(path), factor], path)
    return wire(factor)


@router.delete("/factors/custom/{name}", status_code=204)
def delete_factor(name: str, ctx: Context):
    with ctx.mutation():
        path = ctx.runtime_root / "custom_factors.json"
        factors = load_custom_factors(path)
        if name not in {f.name for f in factors}:
            raise ApiError(404, "factor_missing", "自定义因子不存在")
        save_custom_factors([f for f in factors if f.name != name], path)
    return Response(status_code=204)


@router.get("/factors/catalog")
def factor_catalog(ctx: Context):
    return {
        "items": [
            {**factor_metadata(f), "classification": asdict(classify_factor(f))}
            for f in factor_registry(ctx).list()
        ],
        "intents": INTENT_TERMS,
    }
