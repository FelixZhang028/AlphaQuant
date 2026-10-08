"""Independent FastAPI entry point for the staged React migration."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from quant_platform.api import advanced_tasks, backtests, catalog, data, research, tasks, workspace
from quant_platform.api.common import ApiError, safe_wire
from quant_platform.api.dependencies import ApiContext
from quant_platform.api.responses import HealthResponse
from quant_platform.application.task_store import TaskConflict, TaskMissing
from quant_platform.core.diagnostics import redact_text
from quant_platform.core.exceptions import (
    BacktestValidityError,
    ConfigurationError,
    DataError,
    PluginError,
)
from quant_platform.data.network import friendly_data_error

LOCAL_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
)


def create_app(
    config_path: str | Path = "configs/app.yaml",
    *,
    prior_path: str | Path = "runtime/prior_knowledge.json",
    serve_frontend: bool = False,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        ctx = application.state.context
        if (ctx.runtime_root / "tasks" / "tasks.sqlite3").is_file():
            ctx.tasks.recover()
        yield

    application = FastAPI(
        title="AlphaQuant API",
        version="0.3.0",
        description="迁移阶段本机接口；支持持久化后台任务和同步兼容接口。",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )
    application.state.context = ApiContext(Path(config_path).resolve(), Path(prior_path).resolve())
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(LOCAL_ORIGINS),
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Idempotency-Key"],
        expose_headers=["Location"],
        allow_credentials=False,
    )
    application.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )

    @application.middleware("http")
    async def local_access(request: Request, call_next):
        # Login is deferred: keep this service usable only on the local machine.
        if request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            return JSONResponse(
                {"error": {"code": "local_only", "message": "当前接口仅供本机使用"}}, 403
            )
        origin = request.headers.get("origin")
        if origin and origin not in LOCAL_ORIGINS and origin != str(request.base_url).rstrip("/"):
            return JSONResponse(
                {"error": {"code": "origin_denied", "message": "请求来源未获允许"}}, 403
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": safe_wire(exc.details),
                }
            },
            exc.status,
        )

    @application.exception_handler(RequestValidationError)
    async def invalid_body(request: Request, exc: RequestValidationError):
        # Never echo submitted code, credentials or entire request bodies.
        issues = [
            {"loc": list(error["loc"]), "type": error["type"], "message": redact_text(error["msg"])}
            for error in exc.errors()
        ]
        return JSONResponse(
            {"error": {"code": "invalid_request", "message": "请求参数不合法", "details": issues}},
            422,
        )

    async def invalid_operation(request: Request, exc: Exception):
        return JSONResponse(
            {"error": {"code": "invalid_operation", "message": redact_text(exc)[:1000]}}, 422
        )

    for error_type in (ConfigurationError, PluginError, ValueError, BacktestValidityError):
        application.add_exception_handler(error_type, invalid_operation)

    @application.exception_handler(TaskMissing)
    async def task_missing(request: Request, exc: TaskMissing):
        return JSONResponse({"error": {"code": "task_missing", "message": str(exc)}}, 404)

    @application.exception_handler(TaskConflict)
    async def task_conflict(request: Request, exc: TaskConflict):
        return JSONResponse({"error": {"code": "task_conflict", "message": str(exc)}}, 409)

    @application.exception_handler(FileNotFoundError)
    async def missing_file(request: Request, exc: FileNotFoundError):
        return JSONResponse(
            {"error": {"code": "artifact_missing", "message": "所需数据或结果文件不存在"}}, 404
        )

    @application.exception_handler(DataError)
    async def data_error(request: Request, exc: DataError):
        return JSONResponse(
            {"error": {"code": "data_error", "message": friendly_data_error(exc)}}, 422
        )

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        return JSONResponse(
            {"error": {"code": "internal_error", "message": "操作失败，请查看服务端日志"}}, 500
        )

    @application.get("/api/v1/health", tags=["system"], response_model=HealthResponse)
    def health():
        return {
            "status": "ok",
            "api_version": "0.3.0",
            "execution_mode": "background",
            "authentication": "local_only",
        }

    for router in (
        backtests.router,
        data.router,
        catalog.router,
        tasks.router,
        research.router,
        workspace.router,
        advanced_tasks.router,
    ):
        application.include_router(router, prefix="/api/v1")
    if serve_frontend:
        distribution = Path(__file__).resolve().parents[3] / "frontend/dist"
        if not (distribution / "index.html").is_file():
            raise FileNotFoundError("请先进入 frontend 执行 npm ci 和 npm run build")
        application.mount("/assets", StaticFiles(directory=distribution / "assets"), name="assets")

        @application.get("/favicon.svg", include_in_schema=False)
        def favicon():
            return FileResponse(distribution / "favicon.svg")

        @application.get("/", include_in_schema=False)
        @application.get("/app", include_in_schema=False)
        @application.get("/app/{page:path}", include_in_schema=False)
        def frontend(page: str = ""):
            return FileResponse(distribution / "index.html")

    return application


app = create_app()
