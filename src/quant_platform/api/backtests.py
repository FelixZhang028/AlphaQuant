"""Backtest execution, persisted results, audits and experiment adapters."""

import json
from dataclasses import asdict, replace
from enum import StrEnum
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, Query

from quant_platform.api.common import ApiError, csv_response, resource_path, safe_wire, table, wire
from quant_platform.api.dependencies import ApiContext, context
from quant_platform.api.responses import (
    ComparisonResponse,
    CompletedRunResponse,
    InspectionResponse,
    RestoredRequestResponse,
    RunDetailResponse,
    RunListResponse,
    TableResponse,
)
from quant_platform.api.schemas import (
    BacktestInput,
    CompareInput,
    IdeaInput,
    OptimizationInput,
    RunInput,
    WalkForwardInput,
)
from quant_platform.application.backtest_service import BacktestRequest, BacktestService
from quant_platform.application.guided_research import IDEAS, idea_request, inspect_request
from quant_platform.application.optimization_service import OptimizationRequest, OptimizationService
from quant_platform.application.walk_forward_service import WalkForwardRequest, WalkForwardService
from quant_platform.backtest.credibility import audit_persisted_run
from quant_platform.backtest.diagnosis import generate_diagnosis
from quant_platform.backtest.multiple_testing import annotate_search, load_search, unavailable_selection
from quant_platform.backtest.result import BacktestResult
from quant_platform.backtest.run_store import RunStatus
from quant_platform.backtest.validity import load_persisted_validity
from quant_platform.risk.config import RiskLimits

router = APIRouter(tags=["backtests"])
Context = Annotated[ApiContext, Depends(context)]


class RunTable(StrEnum):
    nav = "nav"
    signals = "signals"
    target_positions = "target_positions"
    orders = "orders"
    fills = "fills"
    closed_trades = "closed_trades"
    positions = "positions"
    risk_events = "risk_events"
    corporate_actions = "corporate_actions"


class ExperimentKind(StrEnum):
    optimization = "optimization"
    walk_forward = "walk-forward"


def build_request(service: BacktestService, body: BacktestInput) -> BacktestRequest:
    if bool(body.plan_id) != bool(body.plan_revision) or (body.plan_id and body.snapshot_run_id):
        raise ApiError(422, "snapshot_conflict", "方案编号与版本需同时提供，且不能混用运行快照")
    if body.plan_id:
        from quant_platform.api.research import restore_plan_snapshot

        restore_plan_snapshot(service, body.plan_id, body.plan_revision)
    if body.snapshot_run_id:
        restore_snapshot(service, body.snapshot_run_id)
    values = body.model_dump(exclude={"risk_limits", "snapshot_run_id", "plan_id", "plan_revision"})
    if body.strategy_plugin == "factor_composite":
        from quant_platform.factors import registry

        registry._DEFAULT_REGISTRY = factor_registry_from_service(service)
    metadata = service.catalog.get_metadata(body.strategy_plugin)
    values["strategy_parameters"] = metadata.validate_parameters(body.strategy_parameters)
    limits = (
        RiskLimits.from_mapping(body.risk_limits.model_dump())
        if body.risk_limits
        else service.default_request().risk_limits
    )
    # Keep execution mode and parent experiment IDs server controlled.
    request = BacktestRequest(**values, risk_limits=limits, baseline_run_id=body.snapshot_run_id)
    service.build_engine(request)
    return request


def request_payload(request: BacktestRequest) -> dict:
    values = wire(request)
    values["snapshot_run_id"] = request.baseline_run_id
    return {key: values.get(key) for key in BacktestInput.model_fields}


def factor_registry_from_service(service):
    from quant_platform.api.dependencies import ApiContext
    from quant_platform.api.workspace import factor_registry

    return factor_registry(
        ApiContext(service.app_config_path, service.runs_root.parent / "prior_knowledge.json")
    )


def restore_snapshot(service: BacktestService, run_id: str) -> None:
    resource_path(service.runs_root, run_id)
    snapshot = service.run_store.load_config(run_id)
    # Preserve historical execution/universe assumptions, but keep artifact storage
    # and market repository anchored to the API's configured instance.
    current_app = service.configs["app"]
    snapshot["app"]["app"] = current_app["app"]
    snapshot["app"]["data"] = current_app["data"]
    service.configs = snapshot


def read_run_table(service: BacktestService, run_id: str, name: RunTable) -> pd.DataFrame:
    directory = resource_path(service.runs_root, run_id)
    path = directory / f"{name.value}.parquet"
    if not path.is_file():
        raise ApiError(404, "artifact_missing", "该运行未保存此明细，旧版结果可能缺少此文件")
    return pd.read_parquet(path)


def record_rows(service, status=None, strategy=None, run_kind=None, q=None):
    rows = []
    for record in service.run_store.list_records():
        if status is not None and record.status != status:
            continue
        if strategy is not None and record.strategy_plugin != strategy:
            continue
        if run_kind is not None and record.run_kind != run_kind:
            continue
        if (
            q
            and q.casefold()
            not in f"{record.strategy_id} {record.run_id} {record.strategy_plugin}".casefold()
        ):
            continue
        row = asdict(record)
        row.pop("path")
        if record.status == RunStatus.SUCCESS:
            validity = load_persisted_validity(resource_path(service.runs_root, record.run_id))
            row.update(
                {
                    key: validity.get(key)
                    for key in ("status", "metrics_reliable", "legacy_unverified")
                    if key != "status"
                }
            )
            row["validity_status"] = validity.get("status")
        rows.append(safe_wire(row))
    return rows


@router.get("/backtests/defaults", response_model=BacktestInput)
def defaults(ctx: Context):
    return request_payload(ctx.backtests().default_request())


@router.get("/research/ideas")
def ideas():
    return [
        {"name": name, "factor": values[0], "description": values[1]}
        for name, values in IDEAS.items()
    ]


@router.post("/research/ideas/prepare", response_model=BacktestInput)
def prepare_idea(body: IdeaInput, ctx: Context):
    service = ctx.backtests()
    if bool(body.plan_id) != bool(body.plan_revision):
        raise ApiError(422, "plan_reference", "方案编号与版本需同时提供")
    if body.plan_id:
        from quant_platform.api.research import restore_plan_snapshot

        restore_plan_snapshot(service, body.plan_id, body.plan_revision)
    request = idea_request(
        service,
        body.idea,
        body.start_date,
        body.end_date,
        body.initial_cash,
        body.top_n,
        body.rebalance,
    )
    service.build_engine(request)
    limits = request.risk_limits
    count = min(body.top_n, len(service.configs["universe"]["universe"]["symbols"]))
    if limits.enabled and not (
        count > 0
        and 1 / count <= limits.max_single_weight + 1e-9
        and count <= limits.max_positions
        and limits.max_total_weight >= 1
        and limits.minimum_cash_ratio == 0
    ):
        raise ApiError(
            409, "allocation_incompatible", "当前等权方案与风险限制不兼容，请调整持仓数或风险规则"
        )
    payload = request_payload(request)
    payload.update(plan_id=body.plan_id, plan_revision=body.plan_revision)
    return payload


@router.post("/backtests/inspect", response_model=InspectionResponse)
def inspect(body: BacktestInput, ctx: Context):
    service = ctx.backtests()
    checks = inspect_request(service, build_request(service, body))
    return {
        "ready": bool(not checks.empty and checks["状态"].eq("通过").all()),
        "checks": table(checks),
    }


@router.post("/backtests/data-request")
def data_request(body: BacktestInput, ctx: Context):
    service = ctx.backtests()
    request = build_request(service, body)
    engine, _ = service.build_engine(request)
    return {
        "start_date": str(engine._warmup_start_date(request.start_date)),
        "end_date": str(request.end_date),
        "datasets": ["security_master", "daily_bars", "corporate_actions", "benchmark_bars"],
        "benchmark_symbols": [engine.benchmark_symbol] if engine.benchmark_symbol else [],
    }


@router.post("/backtests/run", status_code=201, response_model=CompletedRunResponse)
def run(body: RunInput, ctx: Context):
    if not body.confirmed:
        raise ApiError(409, "confirmation_required", "请确认策略规则后再运行")
    with ctx.mutation():
        service = ctx.backtests()
        request = build_request(service, body.request)
        checks = inspect_request(service, request)
        if checks.empty or not checks["状态"].eq("通过").all():
            raise ApiError(409, "data_not_ready", "本次研究的数据检查未通过", table(checks))
        completed = service.run(request)
        from quant_platform.api.research import LOCAL_OWNER, plan_store

        plans = plan_store(service)
        plan = plans.save(
            LOCAL_OWNER,
            body.plan_title or request.strategy_id,
            completed.config_snapshot,
            inputs=body.plan_inputs,
            plan_id=body.request.plan_id,
        )
        plans.link_run(LOCAL_OWNER, plan, completed.result.run_id, completed.config_snapshot)
        return {
            "run_id": completed.result.run_id,
            "status": "SUCCESS",
            "summary": safe_wire(completed.result.summary),
            "validity": safe_wire(completed.result.validity),
        }


@router.get("/runs", response_model=RunListResponse)
def runs(
    ctx: Context,
    status: RunStatus | None = RunStatus.SUCCESS,
    strategy: str | None = None,
    run_kind: str | None = None,
    q: str | None = None,
    include_all_status: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    service = ctx.backtests()
    rows = record_rows(service, None if include_all_status else status, strategy, run_kind, q)
    return {
        "items": rows[offset : offset + limit],
        "run_kinds": sorted({record.run_kind for record in service.run_store.list_records()}),
        "total": len(rows),
        "offset": offset,
        "limit": limit,
    }


@router.get("/runs/export.csv")
def export_runs(
    ctx: Context,
    status: RunStatus | None = RunStatus.SUCCESS,
    strategy: str | None = None,
    run_kind: str | None = None,
    q: str | None = None,
    include_all_status: bool = False,
):
    return csv_response(
        pd.DataFrame(
            record_rows(
                ctx.backtests(), None if include_all_status else status, strategy, run_kind, q
            )
        ),
        "backtest_runs.csv",
    )


@router.post("/runs/compare", response_model=ComparisonResponse)
def compare(body: CompareInput, ctx: Context):
    service = ctx.backtests()
    for run_id in body.run_ids:
        resource_path(service.runs_root, run_id)
    return {
        "metrics": safe_wire(service.run_store.comparison_frame(body.run_ids)),
        "nav": wire(service.run_store.normalized_nav(body.run_ids)),
    }


@router.post("/runs/compare/export.csv")
def export_compare(body: CompareInput, ctx: Context):
    service = ctx.backtests()
    for run_id in body.run_ids:
        resource_path(service.runs_root, run_id)
    frame = service.run_store.comparison_frame(body.run_ids)
    return csv_response(frame, "backtest_comparison.csv")


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def run_detail(run_id: str, ctx: Context):
    service = ctx.backtests()
    path = resource_path(service.runs_root, run_id)
    summary = service.run_store.load_summary(run_id)
    return {
        "run_id": run_id,
        "summary": safe_wire(summary),
        "validity": safe_wire(load_persisted_validity(path)),
        "available_tables": [
            name.value for name in RunTable if (path / f"{name.value}.parquet").is_file()
        ],
    }


@router.get("/runs/{run_id}/request", response_model=RestoredRequestResponse)
def restore_request(run_id: str, ctx: Context):
    service = ctx.backtests()
    resource_path(service.runs_root, run_id)
    return {"request": request_payload(service.request_from_run(run_id)), "baseline_run_id": run_id}


@router.get("/runs/{run_id}/analytics")
def run_analytics(run_id: str, ctx: Context):
    from quant_platform.backtest.metrics import calculate_drawdown_series, calculate_monthly_returns

    service = ctx.backtests()
    nav = read_run_table(service, run_id, RunTable.nav)
    curves = nav[["trade_date"]].copy()
    for key in ("equity", "benchmark_equity"):
        if key in nav and not nav.empty and pd.notna(nav[key].iloc[0]) and nav[key].iloc[0] > 0:
            curves[key] = nav[key] / nav[key].iloc[0]
    return {
        "normalized": safe_wire(curves),
        "drawdown": safe_wire(calculate_drawdown_series(nav)),
        "monthly": safe_wire(calculate_monthly_returns(nav)),
        "linked_oos": sum(
            record.baseline_run_id == run_id and record.run_kind == "walk_forward_oos"
            for record in service.run_store.list_records(successful_only=True)
        ),
    }


@router.get("/runs/{run_id}/audit")
def audit(run_id: str, ctx: Context):
    service = ctx.backtests()
    directory = resource_path(service.runs_root, run_id)
    if not (directory / "summary.json").is_file():
        raise ApiError(404, "result_missing", "该运行尚无可审计结果")
    config = service.run_store.load_config(run_id) if (directory / "config.snapshot.yaml").is_file() else {}
    execution = config.get("execution", {})
    if not isinstance(execution, dict):
        execution = {}
    nested = execution.get("execution")
    if isinstance(nested, dict):
        execution = nested
    historical = execution.get("historical_fees")
    participation = execution.get("max_participation")
    slippage = execution.get("slippage_rate")
    assumptions = pd.DataFrame([
        {"审计假设": "历史分期费率", "取值": "启用" if historical else "停用" if historical is False else "未记录"},
        {"审计假设": "参与率上限", "取值": f"{float(participation):.1%}" if participation is not None else "未记录"},
        {"审计假设": "滑点率", "取值": f"{float(slippage):.3%}" if slippage is not None else "未记录"},
        {"审计假设": "未知状态策略", "取值": str(execution.get("unknown_status_policy", "未记录"))},
    ])
    return {
        **safe_wire(audit_persisted_run(directory)),
        "validity": safe_wire(load_persisted_validity(directory)),
        "execution_assumptions": safe_wire(assumptions),
    }


@router.get("/runs/{run_id}/diagnosis")
def diagnosis(run_id: str, ctx: Context):
    service = ctx.backtests()
    directory = resource_path(service.runs_root, run_id)
    frames = {}
    required = {"nav", "positions", "orders", "fills"}
    for name in RunTable:
        path = directory / f"{name.value}.parquet"
        if path.is_file():
            frames[name.value] = pd.read_parquet(path)
        elif name.value in required:
            raise ApiError(404, "artifact_missing", "该运行缺少生成诊断必需的明细")
        else:
            frames[name.value] = pd.DataFrame()
    frames["targets"] = frames.pop("target_positions")
    frames["trades"] = frames.pop("closed_trades")
    result = BacktestResult(
        run_id=run_id,
        **frames,
        summary=service.run_store.load_summary(run_id),
        validity=load_persisted_validity(directory),
    )
    return safe_wire(generate_diagnosis(result))


@router.get("/runs/{run_id}/tables/{name}", response_model=TableResponse)
def run_table(
    run_id: str,
    name: RunTable,
    ctx: Context,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
):
    return safe_wire(table(read_run_table(ctx.backtests(), run_id, name), offset, limit))


@router.get("/runs/{run_id}/tables/{name}/export.csv")
def export_table(run_id: str, name: RunTable, ctx: Context):
    return csv_response(read_run_table(ctx.backtests(), run_id, name), f"{name.value}.csv")


def experiment_base(service, body):
    resource_path(service.runs_root, body.baseline_run_id)
    summary = service.run_store.load_summary(body.baseline_run_id)
    if not summary.get("metrics_reliable", False):
        raise ApiError(409, "baseline_unreliable", "基准结果未通过可信度检查，不能用于验证实验")
    restore_snapshot(service, body.baseline_run_id)
    base = service.request_from_run(body.baseline_run_id)
    base = replace(
        base, start_date=body.start_date or base.start_date, end_date=body.end_date or base.end_date
    )
    # Reject bad parameter names/types before creating any experiment artifacts.
    metadata = service.catalog.get_metadata(base.strategy_plugin)
    for name, values in body.parameter_grid.items():
        for value in values:
            metadata.validate_parameters({**base.strategy_parameters, name: value})
    service.build_engine(base)
    return base


@router.post("/experiments/optimization/run", status_code=201)
def optimize(body: OptimizationInput, ctx: Context):
    with ctx.mutation():
        service = ctx.backtests()
        result = OptimizationService(service).run(
            OptimizationRequest(
                base_request=experiment_base(service, body),
                parameter_grid={key: tuple(value) for key, value in body.parameter_grid.items()},
                objective=body.objective,
                max_drawdown_limit=body.max_drawdown_limit,
                baseline_run_id=body.baseline_run_id,
                max_workers=body.max_workers,
            )
        )
        frame, selection = optimization_evidence(service, result.output_dir)
        return {"optimization_id": result.optimization_id, "experiments": safe_wire(frame), "selection_bias": safe_wire(selection)}


@router.post("/experiments/walk-forward/run", status_code=201)
def walk_forward(body: WalkForwardInput, ctx: Context):
    with ctx.mutation():
        service = ctx.backtests()
        result = WalkForwardService(service).run(
            WalkForwardRequest(
                base_request=experiment_base(service, body),
                parameter_grid={key: tuple(value) for key, value in body.parameter_grid.items()},
                objective=body.objective,
                max_drawdown_limit=body.max_drawdown_limit,
                baseline_run_id=body.baseline_run_id,
                training_months=body.training_months,
                test_months=body.test_months,
                step_months=body.step_months,
                max_windows=body.max_windows,
            )
        )
        return {
            "validation_id": result.validation_id,
            "summary": safe_wire(result.summary),
            "windows": safe_wire(result.windows),
        }


def experiment_root(ctx, kind):
    service = ctx.backtests()
    return (
        OptimizationService(service).root
        if kind == ExperimentKind.optimization
        else WalkForwardService(service).root
    )


def optimization_evidence(service, directory, fallback=None):
    """Recheck all trial artifacts on every read, never serve stale probabilities."""
    try:
        frame, selection = load_search(directory, service.runs_root)
    except (OSError, ValueError, TypeError, KeyError, OverflowError):
        try:
            frame = pd.read_csv(directory / "results.csv")
        except (OSError, ValueError):
            if fallback is None:
                raise ApiError(404, "artifact_missing", "参数搜索结果文件缺失或损坏，无法读取实验")
            frame = pd.DataFrame(fallback["rows"], columns=fallback["columns"])
        selection = tuple(unavailable_selection("参数搜索记录不完整，无法评估选择偏差。") for _ in range(len(frame)))
    return annotate_search(frame, selection), selection


@router.get("/experiments/{kind}")
def experiments(kind: ExperimentKind, ctx: Context):
    root = experiment_root(ctx, kind)
    items = []
    if root.exists():
        for directory in sorted(root.iterdir(), reverse=True):
            if not directory.is_dir() or not (directory / "request.json").is_file():
                continue
            resource_path(root, directory.name)
            items.append(
                {
                    "id": directory.name,
                    "request": safe_wire(
                        json.loads((directory / "request.json").read_text(encoding="utf-8"))
                    ),
                }
            )
    return {"items": items, "total": len(items)}


@router.get("/experiments/{kind}/{experiment_id}")
def experiment(
    kind: ExperimentKind,
    experiment_id: str,
    ctx: Context,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
):
    path = resource_path(experiment_root(ctx, kind), experiment_id)
    selection = None
    if kind == ExperimentKind.optimization:
        frame, selection = optimization_evidence(ctx.backtests(), path)
    else:
        frame = pd.read_csv(path / "results.csv")
    try:
        request = json.loads((path / "request.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        request = {}
    result = {
        "id": experiment_id,
        "request": safe_wire(request),
        "results": safe_wire(table(frame, offset, limit)),
    }
    if selection is not None:
        result["selection_bias"] = safe_wire(selection[offset:offset + limit])
    if (path / "summary.json").is_file():
        result["summary"] = safe_wire(
            json.loads((path / "summary.json").read_text(encoding="utf-8"))
        )
    return result


@router.get("/experiments/{kind}/{experiment_id}/export.csv")
def export_experiment(kind: ExperimentKind, experiment_id: str, ctx: Context):
    path = resource_path(experiment_root(ctx, kind), experiment_id)
    frame = optimization_evidence(ctx.backtests(), path)[0] if kind == ExperimentKind.optimization else pd.read_csv(path / "results.csv")
    frame = pd.DataFrame(safe_wire(frame)["rows"], columns=frame.columns)
    return csv_response(frame, f"{kind.value}.csv")
