"""Background task lifecycle, persistent logs and result retrieval."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response

from quant_platform.api.common import ApiError, resource_path, safe_wire
from quant_platform.api.dependencies import ApiContext, context
from quant_platform.api.task_schemas import (
    Submission,
    TaskKind,
    TaskListResponse,
    TaskResponse,
    TaskStatus,
)

router = APIRouter(tags=["tasks"], prefix="/tasks")
Context = Annotated[ApiContext, Depends(context)]
IdempotencyKey = Annotated[
    str | None, Header(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")
]


@router.post("", status_code=202, response_model=TaskResponse)
def submit(
    body: Submission, ctx: Context, response: Response, idempotency_key: IdempotencyKey = None
):
    result = ctx.tasks.submit(body, idempotency_key)
    response.headers["Location"] = f"/api/v1/tasks/{result['id']}"
    return safe_wire(result)


@router.get("", response_model=TaskListResponse)
def tasks(
    ctx: Context,
    status: TaskStatus | None = None,
    kind: TaskKind | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    ctx.tasks.recover()
    return safe_wire(ctx.tasks.store.list(status, kind, offset, limit))


@router.get("/{identifier}", response_model=TaskResponse)
def task(identifier: str, ctx: Context):
    ctx.tasks.reconcile(identifier)
    return safe_wire(ctx.tasks.store.get(identifier))


@router.get("/{identifier}/events")
def events(
    identifier: str,
    ctx: Context,
    after: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=1000),
):
    ctx.tasks.reconcile(identifier)
    items = ctx.tasks.store.events(identifier, after, limit)
    return {"items": items, "next_after": items[-1]["seq"] if items else after}


@router.get("/{identifier}/result")
def result(identifier: str, ctx: Context):
    ctx.tasks.reconcile(identifier)
    output = ctx.tasks.store.result(identifier)
    if ctx.tasks.store.get(identifier)["kind"] == "optimization":
        from quant_platform.api.backtests import optimization_evidence
        from quant_platform.application.optimization_service import OptimizationService

        service = ctx.backtests()
        root = OptimizationService(service).root
        try:
            directory = resource_path(root, output["optimization_id"])
        except ApiError as exc:
            if exc.status != 404:
                raise
            directory = root / "__missing_optimization__"
        frame, selection = optimization_evidence(service, directory, output["experiments"])
        output = {**output, "experiments": safe_wire(frame), "selection_bias": safe_wire(selection)}
    return safe_wire(output)


@router.post("/{identifier}/cancel", response_model=TaskResponse)
def cancel(identifier: str, ctx: Context):
    ctx.tasks.reconcile(identifier)
    result = ctx.tasks.store.cancel(identifier)
    if result["status"] in {"CANCELLED", "CANCEL_REQUESTED"}:
        ctx.tasks.store.event(
            identifier, {"stage": "cancel_requested", "message": "已提交取消请求"}
        )
    return safe_wire(result)


@router.post("/{identifier}/retry", status_code=202, response_model=TaskResponse)
def retry(
    identifier: str, ctx: Context, response: Response, idempotency_key: IdempotencyKey = None
):
    result = ctx.tasks.retry(identifier, idempotency_key)
    response.headers["Location"] = f"/api/v1/tasks/{result['id']}"
    return result


@router.get("/{identifier}/input")
def inputs(identifier: str, ctx: Context):
    item = ctx.tasks.store.get(identifier, private=True)
    # Only the typed submitted request is exposed, never config snapshots or credentials.
    return {"kind": item["kind"], "input": safe_wire(item["input"])}
