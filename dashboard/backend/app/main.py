"""
FastAPI 应用入口。

启动方式（在 backend/ 目录下）：
    pip install -r requirements.txt
    uvicorn app.main:app --reload

REST 文档：http://localhost:8000/docs
WebSocket：ws://localhost:8000/ws/dashboard
"""
import logging
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .database import init_db
from .routes.admin import router as admin_router
from .routes.agent_lab import router as agent_lab_router
from .routes.auth import router as auth_router
from .routes.backtests import router as backtests_router
from .routes.stats import router as stats_router
from .routes.strategies import router as strategies_router
from .routes.workspace import router as workspace_router
from .ws import router as ws_router

logger = logging.getLogger("uvicorn.error")

app = FastAPI(
    title="智投引擎 · 后端",
    description="为官网/功能台/管理后台提供认证与实时监控数据（当前业务指标为模拟数据，可替换为真实数据源）",
    version="1.0.0",
)


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

# 允许前端开发服务器跨域访问：
#   官网/功能台   http://127.0.0.1:5273
#   监控大屏前端  http://127.0.0.1:5174
#   独立管理后台  http://127.0.0.1:5175
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5273",
        "http://127.0.0.1:5273",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(strategies_router)
app.include_router(backtests_router)
app.include_router(admin_router)
app.include_router(stats_router)
app.include_router(workspace_router)
app.include_router(agent_lab_router)
app.include_router(ws_router)


@app.get("/", summary="健康检查")
def root():
    return {"status": "ok", "service": "智投引擎后端", "docs": "/docs"}
