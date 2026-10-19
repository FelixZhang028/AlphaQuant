"""
FastAPI 应用入口。

启动方式（在 backend/ 目录下）：
    pip install -r requirements.txt
    uvicorn app.main:app --reload

REST 文档：FELLOWQUANT_API_DOCS=on 时在 http://localhost:8000/docs（正式部署默认关闭）

部署时的设置（都写在 .env 里）：
- FELLOWQUANT_CORS_ORIGINS：允许跨域访问的网页地址，逗号分开；前后端同一个地址时不需要
- FELLOWQUANT_STATIC_DIR：打包好的前端目录（landing/dist），后端直接提供网页，整个网站只有一个地址
- FELLOWQUANT_ADMIN_DIR：打包好的管理后台（admin/dist），在 /admin/ 提供
- FELLOWQUANT_MAX_BODY_MB：一次请求最大多少 MB（默认 5）
"""
import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .quant.backup import BackupScheduler
from .quant.daily_schedule import DailyScheduler
from .quant.fundamentals_schedule import FundamentalsScheduler
from .routes.admin import router as admin_router
from .routes.agent_lab import router as agent_lab_router
from .routes.auth import router as auth_router
from .routes.backtests import router as backtests_router
from .routes.settings import router as settings_router
from .routes.workspace import _data_jobs
from .routes.workspace import router as workspace_router

logger = logging.getLogger("uvicorn.error")


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    return default if not value else value not in ("0", "off", "false", "no")


API_DOCS = _flag("FELLOWQUANT_API_DOCS", False)
STATIC_DIR = os.getenv("FELLOWQUANT_STATIC_DIR", "").strip()
ADMIN_DIR = os.getenv("FELLOWQUANT_ADMIN_DIR", "").strip()
DEV_ORIGINS = [
    #   官网/功能台   http://127.0.0.1:5273（Vite 开发服务器也用 5173）
    #   管理后台      http://127.0.0.1:5175
    f"http://{host}:{port}" for port in (5273, 5173, 5175) for host in ("localhost", "127.0.0.1")
]
CORS_ORIGINS = [origin.strip().rstrip("/") for origin in os.getenv("FELLOWQUANT_CORS_ORIGINS", "").split(",") if origin.strip()] or DEV_ORIGINS
try:
    MAX_BODY_BYTES = int(float(os.getenv("FELLOWQUANT_MAX_BODY_MB", "") or 5) * 1024 * 1024)
except ValueError:
    MAX_BODY_BYTES = 5 * 1024 * 1024


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 每个交易日收盘后自动更新全市场数据（FELLOWQUANT_DAILY_UPDATE=off 关闭）；财报季每周六更新财务数据
    # （FELLOWQUANT_FUNDAMENTALS_UPDATE=off 关闭）；每天备份一次用户数据。
    scheduler = DailyScheduler(_data_jobs())
    fundamentals = FundamentalsScheduler(_data_jobs())
    backups = BackupScheduler()
    scheduler.start()
    fundamentals.start()
    backups.start()
    try:
        yield
    finally:
        scheduler.stop()
        fundamentals.stop()
        backups.stop()


app = FastAPI(
    title="FellowQuant · 后端",
    description="FellowQuant 的认证、研究与数据接口",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if API_DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if API_DOCS else None,
)


# 浏览器的安全设置：不让别的网站把页面嵌进去、不猜测文件类型、跳转时不带完整地址。
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# 后端直接提供网页时的内容安全策略：只运行本站的脚本，只连接本站的接口。
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; img-src 'self' data: blob:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"
)


@app.middleware("http")
async def guard_requests(request: Request, call_next):
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"detail": "请求内容太大"})
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if STATIC_DIR or ADMIN_DIR:
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
            # 网页每次都向服务器确认是否更新：发布新版本以后，浏览器不会继续用引用旧文件的页面。
            response.headers.setdefault("Cache-Control", "no-cache")
        elif "/assets/" in request.url.path and response.status_code == 200:
            # 打包出的文件名带内容指纹，内容变了名字就变，可以放心长期缓存。
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    return response


def _sanitize_error(exc: Exception) -> str:
    """清洗异常信息，去除技术细节，只保留用户可读消息。"""
    text = str(exc).strip()
    if not text:
        return "服务器内部错误，请稍后重试"
    # 去除 Python 异常类名前缀
    text = re.sub(r"^[A-Z]\w*(?:Error|Exception|Warning|Interrupt):\s*", "", text)
    # 去除引擎错误码前缀：MISSING_CORPORATE_ACTION: xxx
    text = re.sub(r"^[A-Z][A-Z_]{2,}:\s*", "", text)
    # 去除文件路径和行号
    text = re.sub(r'File ["\'][^"\']+["\'],\s*line\s*\d+[^)]*', "", text)
    text = re.sub(r"[\w./\\-]+\.py:\d+:\s*", "", text)
    # 去除 traceback 前缀
    if "Traceback" in text:
        lines = [l.strip() for l in text.split("\n") if l.strip() and not l.startswith("Traceback") and not l.startswith('  File')]
        text = lines[-1] if lines else ""
    text = text.strip()
    if not text or len(text) < 2:
        return "服务器内部错误，请稍后重试"
    return text


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """参数校验失败：不返回 pydantic 的英文/代码层细节，统一友好提示。"""
    # Pydantic errors include raw input, which can contain passwords and API keys.
    fields = [{"loc": error["loc"], "type": error["type"]} for error in exc.errors()[:3]]
    logger.info("Validation error on %s %s: %s", request.method, request.url.path, fields)
    return JSONResponse(
        status_code=422,
        content={"detail": "请求参数不正确，请检查输入后重试"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理：未预期的异常统一返回 500 + 友好消息，不泄露 traceback。"""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )

# 启动时建表（users 等）
init_db()

# 允许跨域访问的网页地址：默认是本机的开发服务器；部署时用 FELLOWQUANT_CORS_ORIGINS 设置。
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(backtests_router)
app.include_router(admin_router)
app.include_router(workspace_router)
app.include_router(agent_lab_router)
app.include_router(settings_router)


@app.get("/api/health", summary="健康检查")
def health():
    return {"status": "ok", "service": "FellowQuant 后端"}


if ADMIN_DIR:
    # 管理后台：只有管理员账户能登录，接口另外检查管理员权限。
    app.mount("/admin", StaticFiles(directory=Path(ADMIN_DIR), html=True), name="admin")
if STATIC_DIR:
    # 后端直接提供打包好的网页：/、/app.html、/auth.html……接口仍在 /api 下（前面已经注册）。
    app.mount("/", StaticFiles(directory=Path(STATIC_DIR), html=True), name="site")
else:
    @app.get("/", summary="健康检查")
    def root():
        return {"status": "ok", "service": "FellowQuant 后端"}
