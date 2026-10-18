"""限制登录、注册、找回密码的频率，防止猜密码和批量注册。

按“最近一段时间里的次数”计数（滑动窗口），只保存在后端进程的内存里：部署时运行一个后端进程，
重启后重新计数。客户端地址默认用连接的来源地址；放在 Cloudflare、Nginx 后面时，来源都是代理，
要用 ``FELLOWQUANT_CLIENT_IP_HEADER`` 指定代理传来的真实地址（Cloudflare 是 ``CF-Connecting-IP``）。
``FELLOWQUANT_RATE_LIMITS=off`` 关闭（只用于测试）。
"""

from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def enabled() -> bool:
    return os.getenv("FELLOWQUANT_RATE_LIMITS", "on").strip().lower() not in ("0", "off", "false", "no")


def client_ip(request: Request) -> str:
    header = os.getenv("FELLOWQUANT_CLIENT_IP_HEADER", "").strip()
    if header:
        value = request.headers.get(header, "").split(",")[0].strip()
        if value:
            return value
    return request.client.host if request.client else "unknown"


def _recent(key: str, window: float, now: float) -> deque[float]:
    hits = _hits[key]
    while hits and hits[0] <= now - window:
        hits.popleft()
    return hits


def _refuse(wait: float, message: str) -> None:
    minutes = max(1, math.ceil(wait / 60))
    raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"{message}，请 {minutes} 分钟后再试。", headers={"Retry-After": str(math.ceil(wait))})


def check(key: str, limit: int, window: float, message: str, *, record: bool = True) -> None:
    """Refuse with 429 when ``key`` already has ``limit`` hits in the last ``window`` seconds; else count this one."""

    if not enabled():
        return
    now = time.monotonic()
    with _lock:
        hits = _recent(key, window, now)
        if len(hits) >= limit:
            _refuse(hits[0] + window - now, message)
        if record:
            hits.append(now)


def record(key: str, window: float) -> None:
    """Count one hit for ``key`` without checking (for example a failed login)."""

    if not enabled():
        return
    now = time.monotonic()
    with _lock:
        _recent(key, window, now).append(now)


def clear(key: str) -> None:
    with _lock:
        _hits.pop(key, None)


def reset() -> None:
    """Forget every count (tests)."""

    with _lock:
        _hits.clear()
