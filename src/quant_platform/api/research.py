"""Research plan snapshots, external trade evidence and existing backfill jobs."""

from copy import deepcopy
from pathlib import Path
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends

from quant_platform.api.backtests import build_request, request_payload
from quant_platform.api.common import ApiError, resource_path, safe_wire, table
from quant_platform.api.dependencies import ApiContext, context
from quant_platform.api.workspace_schemas import (
    BackfillInput,
    ExternalInput,
    PlanCompareInput,
    PlanInput,
)
from quant_platform.application.data_jobs import DataJobs
from quant_platform.application.research_plans import (
    ResearchPlanStore,
    configuration_diff,
    owner_key,
)
from quant_platform.core.diagnostics import redact_text
from quant_platform.forensics.checks import check_trades, load_evidence, markdown_report
from quant_platform.forensics.parsing import detect_columns, parse_trades, read_material

router = APIRouter(tags=["research"])
Context = Annotated[ApiContext, Depends(context)]
LOCAL_OWNER = owner_key("__local__")


def plan_store(service):
    return ResearchPlanStore(
        Path(service.configs["app"]["app"]["runtime_dir"]) / "state/research_plans.sqlite3"
    )


def restore_plan_snapshot(service, plan_id, revision):
    store = plan_store(service)
    plan = store.load(LOCAL_OWNER, plan_id, revision)
    snapshot = deepcopy(plan["snapshot"])
    snapshot["app"]["app"] = service.configs["app"]["app"]
    snapshot["app"]["data"] = service.configs["app"]["data"]
    service.configs = snapshot
    return plan


@router.get("/research/plans")
def plans(ctx: Context):
    store = plan_store(ctx.backtests())
    return {
        "scope": "local_workspace",
        "items": [
            {
                **safe_wire({k: v for k, v in p.items() if k not in {"snapshot", "owner"}}),
                "runs": store.runs(LOCAL_OWNER, p["plan_id"], p["revision"]),
            }
            for p in store.list(LOCAL_OWNER)
        ],
    }


@router.post("/research/plans", status_code=201)
def save_plan(body: PlanInput, ctx: Context):
    with ctx.mutation():
        service = ctx.backtests()
        if bool(body.run_id) == bool(body.request):
            raise ApiError(422, "plan_input", "请选择历史运行或当前请求中的一项")
        if body.run_id:
            resource_path(service.runs_root, body.run_id)
            snapshot = service.run_store.load_config(body.run_id)
        else:
            _, snapshot = service.build_engine(build_request(service, body.request))
        store = plan_store(service)
        result = store.save(LOCAL_OWNER, body.title, snapshot, body.inputs, body.plan_id)
        if body.run_id:
            store.link_run(LOCAL_OWNER, result, body.run_id, snapshot)
    return {k: v for k, v in safe_wire(result).items() if k not in {"owner", "snapshot"}}


@router.get("/research/plans/{plan_id}/{revision}/request")
def plan_request(plan_id: str, revision: int, ctx: Context):
    service = ctx.backtests()
    plan = restore_plan_snapshot(service, plan_id, revision)
    request = request_payload(service.default_request())
    request.update(plan_id=plan_id, plan_revision=revision, snapshot_run_id=None)
    return {"request": request, "title": plan["title"], "inputs": safe_wire(plan["inputs"])}


@router.post("/research/plans/compare")
def compare_plans(body: PlanCompareInput, ctx: Context):
    service = ctx.backtests()
    store = plan_store(service)
    chosen = [store.load(LOCAL_OWNER, ref.plan_id, ref.revision) for ref in body.versions]
    results = []
    for plan in chosen:
        runs = store.runs(LOCAL_OWNER, plan["plan_id"], plan["revision"])
        row = {
            "title": plan["title"],
            "revision": plan["revision"],
            "run_id": None,
            "summary": None,
            "status": "未运行",
        }
        if runs:
            row["run_id"] = runs[-1]
            path = service.runs_root / runs[-1] / "summary.json"
            if path.is_file():
                import json

                row.update(summary=json.loads(path.read_text(encoding="utf-8")), status="已运行")
            else:
                row["status"] = "结果不可读"
        results.append(row)
    return {
        "differences": table(pd.DataFrame(configuration_diff(chosen))),
        "results": safe_wire(results),
        "warning": "区间、股票池、费用或风控不同的结果不可直接排名；方案不复制行情数据。",
    }


@router.post("/audits/external/preview")
def external_preview(body: ExternalInput):
    frame = read_material(body.content)
    return {
        "preview": table(frame, limit=10),
        "mapping": detect_columns(frame),
        "total": len(frame),
    }


@router.post("/audits/external/check")
def external_check(body: ExternalInput, ctx: Context):
    frame = read_material(body.content)
    parsed = parse_trades(frame, body.mapping or detect_columns(frame), body.unit)
    if not parsed.errors.empty:
        raise ApiError(422, "trade_rows_invalid", "请修正错误行后再检查", table(parsed.errors))
    duplicates = parsed.trades.duplicated(
        ["date", "symbol", "side", "quantity", "price"], keep=False
    )
    if duplicates.any() and not body.duplicate_confirmed:
        raise ApiError(
            409,
            "duplicate_confirmation",
            "存在重复成交，请核对后明确确认",
            table(parsed.trades[duplicates]),
        )
    master, bars = load_evidence(ctx.data().repository.root, parsed.trades)
    findings = check_trades(parsed.trades, master, bars, raw_prices=body.raw_prices)
    return {
        "findings": safe_wire(findings),
        "markdown": markdown_report(findings),
        "counts": findings["结论"].value_counts().to_dict(),
        "total_trades": len(frame),
    }


def backfill_jobs(ctx):
    return DataJobs(ctx.runtime_root / "data_jobs", str(ctx.config_path))


@router.get("/data/backfill/jobs")
def backfill_records(ctx: Context):
    return {"items": safe_wire(backfill_jobs(ctx).records())}


@router.post("/data/backfill/jobs", status_code=202)
def start_backfill(body: BackfillInput, ctx: Context):
    with ctx.mutation():
        return safe_wire(backfill_jobs(ctx).start(body.start_date, body.end_date, body.datasets))


@router.post("/data/backfill/jobs/{identifier}/stop")
def stop_backfill(identifier: str, ctx: Context):
    backfill_jobs(ctx).stop(identifier)
    return {"stop_requested": True}


@router.post("/data/backfill/jobs/{identifier}/retry", status_code=202)
def retry_backfill(identifier: str, ctx: Context):
    from datetime import date

    jobs = backfill_jobs(ctx)
    item = next((j for j in jobs.records() if j["id"] == identifier), None)
    if item is None:
        raise ApiError(404, "job_missing", "回填任务不存在")
    if item["status"] not in {"FAILED", "PARTIAL", "STOPPED", "INTERRUPTED"}:
        raise ApiError(409, "job_active", "该状态不能继续回填")
    with ctx.mutation():
        return safe_wire(
            jobs.start(
                date.fromisoformat(item["start_date"]),
                date.fromisoformat(item["end_date"]),
                item["datasets"],
            )
        )


@router.get("/data/backfill/jobs/{identifier}/log")
def backfill_log(identifier: str, ctx: Context):
    return {"text": redact_text(backfill_jobs(ctx).log(identifier))[-32768:]}
