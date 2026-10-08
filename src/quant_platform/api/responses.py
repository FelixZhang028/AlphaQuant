"""Stable response envelopes for a typed React client."""

from typing import Any, Literal

from pydantic import BaseModel

from quant_platform.api.schemas import BacktestInput
from quant_platform.backtest.run_store import RunStatus


class HealthResponse(BaseModel):
    status: Literal["ok"]
    api_version: str
    execution_mode: Literal["background"]
    authentication: Literal["local_only"]


class TableResponse(BaseModel):
    columns: list[str]
    rows: list[dict[str, Any]]
    total: int
    offset: int
    limit: int | None


class InspectionResponse(BaseModel):
    ready: bool
    checks: TableResponse


class CompletedRunResponse(BaseModel):
    run_id: str
    status: Literal["SUCCESS"]
    summary: dict[str, Any]
    validity: dict[str, Any]


class RunItem(BaseModel):
    run_id: str
    status: RunStatus
    created_at: str
    updated_at: str
    strategy_plugin: str
    strategy_id: str
    start_date: str
    end_date: str
    error: str | None
    run_kind: str
    parent_experiment_id: str | None
    baseline_run_id: str | None
    validity_status: str | None = None
    metrics_reliable: bool | None = None
    legacy_unverified: bool | None = None


class RunListResponse(BaseModel):
    items: list[RunItem]
    run_kinds: list[str]
    total: int
    offset: int
    limit: int


class RunDetailResponse(BaseModel):
    run_id: str
    summary: dict[str, Any]
    validity: dict[str, Any]
    available_tables: list[str]


class RestoredRequestResponse(BaseModel):
    request: BacktestInput
    baseline_run_id: str


class ComparisonResponse(BaseModel):
    metrics: TableResponse
    nav: TableResponse
