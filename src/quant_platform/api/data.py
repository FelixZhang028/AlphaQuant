"""Local market queries, coverage, full exports and normal data updates."""

from dataclasses import replace
from datetime import date
from enum import StrEnum
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, Query

from quant_platform.api.common import ApiError, csv_response, safe_wire, table
from quant_platform.api.dependencies import ApiContext, context
from quant_platform.api.responses import TableResponse
from quant_platform.api.schemas import SymbolInput, UniverseFilterInput, UpdateInput
from quant_platform.application.manifest_summary import add_provider_route_summary
from quant_platform.application.readiness_service import PlatformReadinessService
from quant_platform.application.universe_service import UniverseManagementService

router = APIRouter(tags=["data"])
Context = Annotated[ApiContext, Depends(context)]


class MarketTable(StrEnum):
    daily_bars = "daily_bars"
    benchmark_bars = "benchmark_bars"
    security_master = "security_master"
    data_manifests = "data_manifests"
    trade_calendar = "trade_calendar"
    corporate_actions = "corporate_actions"
    universe_membership = "universe_membership"
    security_exposures = "security_exposures"
    delisting_settlements = "delisting_settlements"


def filtered_table(ctx, name, symbols, start_date, end_date):
    if start_date and end_date and start_date > end_date:
        raise ApiError(422, "invalid_dates", "开始日期不能晚于结束日期")
    service = ctx.data()
    if name == MarketTable.daily_bars:
        frame = service.repository.get_daily_bars(symbols, start_date, end_date)
    else:
        frame = service.repository.read_table(name.value)
        if not frame.empty:
            if symbols:
                if "symbol" not in frame.columns:
                    raise ApiError(422, "unsupported_filter", "该数据集不支持按证券过滤")
                frame = frame.loc[frame.symbol.isin(symbols)]
            date_col = {
                "trade_calendar": "cal_date",
                "corporate_actions": "ex_date",
                "universe_membership": "effective_from",
                "security_exposures": "date",
                "data_manifests": "completed_at",
            }.get(name.value, "trade_date")
            if start_date or end_date:
                if date_col not in frame.columns:
                    raise ApiError(422, "unsupported_filter", "该数据集不支持日期过滤")
                dates = pd.to_datetime(frame[date_col], utc=True).dt.date
                if start_date:
                    frame = frame.loc[dates.ge(start_date)]
                    dates = dates.loc[frame.index]
                if end_date:
                    frame = frame.loc[dates.le(end_date)]
            keys = [key for key in (date_col, "symbol") if key in frame.columns]
            if keys:
                frame = frame.sort_values(keys, ascending=name != MarketTable.data_manifests)
    if name == MarketTable.data_manifests and not frame.empty:
        frame = add_provider_route_summary(frame)
        # Provider errors and request parameters can contain credentials.
        frame = pd.DataFrame(safe_wire(frame)["rows"], columns=frame.columns)
    return frame


@router.get("/readiness")
def readiness(ctx: Context):
    return safe_wire(PlatformReadinessService(ctx.config_path).inspect())


@router.get("/data/overview")
def overview(ctx: Context):
    return safe_wire(ctx.data().overview().to_dict())


@router.get("/data/sources", response_model=TableResponse)
def sources(ctx: Context):
    return safe_wire(ctx.data().market_source_status())


@router.get("/data/coverage", response_model=TableResponse)
def coverage(ctx: Context, offset: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000)):
    return safe_wire(table(ctx.data().overview().per_symbol, offset, limit))


@router.get("/data/coverage/export.csv")
def export_coverage(ctx: Context):
    return csv_response(ctx.data().overview().per_symbol, "configured_stock_coverage.csv")


@router.get("/data/closed-loop")
def closed_loop(ctx: Context):
    return safe_wire(ctx.data().closed_loop_status())


@router.get("/data/tables/{name}", response_model=TableResponse)
def data_table(
    name: MarketTable,
    ctx: Context,
    symbols: Annotated[list[str] | None, Query()] = None,
    start_date: date | None = None,
    end_date: date | None = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=5000),
):
    return safe_wire(table(filtered_table(ctx, name, symbols, start_date, end_date), offset, limit))


@router.get("/data/tables/{name}/export.csv")
def export_data(
    name: MarketTable,
    ctx: Context,
    symbols: Annotated[list[str] | None, Query()] = None,
    start_date: date | None = None,
    end_date: date | None = None,
):
    return csv_response(
        filtered_table(ctx, name, symbols, start_date, end_date), f"{name.value}.csv"
    )


@router.post("/data/update")
def update(body: UpdateInput, ctx: Context):
    with ctx.mutation():
        service = ctx.data()
        # Use the same supervisor state and update lock as the old interface.
        from pathlib import Path

        from quant_platform.application.data_jobs import DataJobs
        from quant_platform.core.config import require_mapping

        runtime = Path(str(require_mapping(service.app, "app")["runtime_dir"]))
        if DataJobs(runtime / "data_jobs", str(ctx.config_path)).active():
            raise ApiError(409, "backfill_active", "回填任务正在执行，请完成后再更新")
        chosen = set(body.datasets)
        result = service.update_all(
            body.start_date,
            body.end_date,
            include_security_master="security_master" in chosen,
            include_market="daily_bars" in chosen,
            include_corporate_actions="corporate_actions" in chosen,
            include_benchmark="benchmark_bars" in chosen,
            market_source_order=body.market_source_order,
            allow_market_fallback=body.allow_market_fallback,
            benchmark_symbols=body.benchmark_symbols,
        )
        return {"results": safe_wire(result)}


@router.get("/universe")
def universe(ctx: Context):
    service = UniverseManagementService(ctx.config_path)
    return {"settings": safe_wire(service.load()), "symbols": safe_wire(service.describe_symbols())}


@router.get("/universe/search", response_model=TableResponse)
def search(ctx: Context, q: str = "", limit: int = Query(50, ge=1, le=200)):
    return safe_wire(
        UniverseManagementService(ctx.config_path).search_security_master(q, limit=limit)
    )


@router.post("/universe/symbols")
def add_symbols(body: SymbolInput, ctx: Context):
    with ctx.mutation():
        return safe_wire(
            UniverseManagementService(ctx.config_path).add_symbols(tuple(body.symbols))
        )


@router.post("/universe/symbols/remove")
def remove_symbols(body: SymbolInput, ctx: Context):
    with ctx.mutation():
        return safe_wire(UniverseManagementService(ctx.config_path).remove_symbols(body.symbols))


@router.put("/universe/filters")
def filters(body: UniverseFilterInput, ctx: Context):
    with ctx.mutation():
        service = UniverseManagementService(ctx.config_path)
        settings = replace(service.load(), **body.model_dump())
        service.save(settings)
        return safe_wire(settings)
