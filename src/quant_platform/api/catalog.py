"""Strategy discovery, visual packages, factors and prior knowledge."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.api.backtests import build_request, request_payload
from quant_platform.api.common import ApiError, safe_wire, wire
from quant_platform.api.dependencies import ApiContext, context
from quant_platform.api.schemas import (
    CopyInput,
    FactorEvaluationInput,
    KnowledgeInput,
    PackageInput,
    PackageRequestInput,
)
from quant_platform.application.strategy_studio_service import (
    StrategyPackage,
    StrategyStudioService,
)
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.strategies.rule_schema import RuleStrategyDefinition
from quant_platform.strategies.templates import STYLE_LABELS, beginner_templates

router = APIRouter(tags=["catalog"])
Context = Annotated[ApiContext, Depends(context)]


@router.get("/strategies")
def strategies(ctx: Context):
    service = ctx.backtests()
    return {
        "items": wire(service.available_strategies()),
        "load_errors": safe_wire(service.user_strategy_errors),
    }


@router.get("/strategies/templates")
def templates():
    return {"items": wire(beginner_templates()), "styles": STYLE_LABELS}


@router.get("/strategies/templates/{template_id}/{style}")
def template(template_id: str, style: str, ctx: Context):
    return StrategyStudioService(ctx.backtests()).template_package(template_id, style).to_dict()


@router.post("/strategies/packages/validate")
def validate_package(body: PackageInput):
    definition = RuleStrategyDefinition.from_mapping(body.definition)
    definition.validate()
    return {
        "valid": True,
        "definition": definition.to_dict(),
        "minimum_history_days": definition.minimum_history_days,
    }


@router.get("/strategies/packages")
def packages(ctx: Context):
    return {
        "items": [item.to_dict() for item in StrategyStudioService(ctx.backtests()).store.list()]
    }


@router.post("/strategies/packages", status_code=201)
def save_package(body: PackageInput, ctx: Context):
    with ctx.mutation():
        studio = StrategyStudioService(ctx.backtests())
        if body.revision_of:
            studio.store.load(body.revision_of)
        definition = RuleStrategyDefinition.from_mapping(body.definition)
        source = f"revision:{body.revision_of}" if body.revision_of else "visual_builder"
        return studio.store.save(
            definition, top_n=body.top_n, rebalance=body.rebalance, source=source
        ).to_dict()


@router.get("/strategies/packages/{package_id}")
def package(package_id: str, ctx: Context):
    return StrategyStudioService(ctx.backtests()).store.load(package_id).to_dict()


@router.post("/strategies/packages/{package_id}/copy", status_code=201)
def copy_package(package_id: str, body: CopyInput, ctx: Context):
    with ctx.mutation():
        return (
            StrategyStudioService(ctx.backtests()).store.copy(package_id, name=body.name).to_dict()
        )


@router.post("/strategies/packages/prepare")
def prepare_package(body: PackageRequestInput, ctx: Context):
    service = ctx.backtests()
    studio = StrategyStudioService(service)
    package = StrategyPackage.from_mapping(body.package)
    base = build_request(service, body.base_request) if body.base_request else None
    request = studio.build_request(package, base_request=base)
    return {"request": request_payload(request), "warnings": list(studio.preflight(package))}


@router.get("/factors")
def factors(ctx: Context, q: str = "", category: str | None = None, source: str | None = None):
    from quant_platform.api.workspace import factor_metadata, factor_registry

    items = factor_registry(ctx).list(category)
    items = [
        item
        for item in items
        if (source is None or item.source == source)
        and q.casefold() in f"{item.name} {item.display_name} {item.description}".casefold()
    ]
    return {"items": [factor_metadata(f) for f in items], "total": len(items)}


@router.post("/factors/evaluate")
def evaluate(body: FactorEvaluationInput, ctx: Context):
    from quant_platform.api.workspace import factor_registry

    try:
        factor = factor_registry(ctx).get(body.factor_name)
    except KeyError as exc:
        raise ApiError(404, "factor_missing", "因子不存在") from exc
    with ctx.mutation():
        report = FactorEvaluator(ctx.data().repository).evaluate(
            factor,
            body.start_date,
            body.end_date,
            symbols=body.symbols,
            horizon=body.horizon,
            n_groups=body.n_groups,
            neutralization=body.neutralization,
        )
        return safe_wire(report)


@router.get("/knowledge")
def knowledge(
    ctx: Context,
    q: str = "",
    source: str | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    entries = PriorKnowledgeStore(ctx.prior_path).list()
    selected = [
        item
        for item in entries
        if (source is None or item.source == source)
        and q.casefold() in f"{item.content} {item.source}".casefold()
    ]
    return {
        "items": wire(selected[offset : offset + limit]),
        "total": len(selected),
        "all_count": len(entries),
        "sources": sorted({item.source for item in entries}),
        "latest_update": entries[0].created_at.isoformat() if entries else None,
    }


@router.post("/knowledge", status_code=201)
def add_knowledge(body: KnowledgeInput, ctx: Context):
    with ctx.mutation():
        return PriorKnowledgeStore(ctx.prior_path).add(body.content, body.source).to_dict()


@router.delete("/knowledge/{entry_id}", status_code=204)
def delete_knowledge(entry_id: str, ctx: Context):
    with ctx.mutation():
        store = PriorKnowledgeStore(ctx.prior_path)
        if not any(entry.id == entry_id for entry in store.list()):
            raise ApiError(404, "not_found", "知识条目不存在")
        store.delete(entry_id)
    return Response(status_code=204)
