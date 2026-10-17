"""所有用户共用一台服务器：耗时的计算（回测、参数验证、因子评估、组合研究）要排队、限时，算过的结果复用。

- 每个用户同一时间只算一件（``FELLOWQUANT_COMPUTE_PER_USER``，默认 1）；
- 全站同时最多算 ``FELLOWQUANT_COMPUTE_SLOTS`` 件（默认 CPU 核数的一半，在 2 到 4 之间）；
  满了直接告诉用户稍后再试，不排队占着连接；
- 一件计算最多 ``FELLOWQUANT_COMPUTE_TIMEOUT`` 秒（默认 600）：长循环在安全的地方检查时间，
  超时就停下（见 ``quant_platform.core.deadline``）；
- 因子研究的结果按 用户、请求内容、本地数据的版本 记住最近 ``FELLOWQUANT_COMPUTE_CACHE`` 份（默认 64），
  再算同样的东西直接返回；数据一更新（每天自动更新以后）版本就变，旧结果不再使用。

计数在一个后端进程里（部署时只运行一个后端进程）。
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder

from quant_platform.core import deadline
from quant_platform.core.deadline import ComputationTimeout


def _setting(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "")))
    except ValueError:
        return default


def slots() -> int:
    return _setting("FELLOWQUANT_COMPUTE_SLOTS", min(4, max(2, (os.cpu_count() or 2) // 2)))


def per_user() -> int:
    return _setting("FELLOWQUANT_COMPUTE_PER_USER", 1)


def timeout_seconds() -> int:
    return _setting("FELLOWQUANT_COMPUTE_TIMEOUT", 600)


def cache_size() -> int:
    return _setting("FELLOWQUANT_COMPUTE_CACHE", 64)


_lock = threading.Lock()
_running: dict[Any, int] = {}
_total = 0


def running() -> dict[str, int]:
    """How many computations are running now (for tests and diagnostics)."""

    with _lock:
        return {"total": _total, "users": sum(1 for count in _running.values() if count)}


@contextmanager
def computing(user: dict[str, Any]) -> Iterator[None]:
    """Hold one computation slot for ``user`` while the block runs, with the time limit.

    A full slot is refused with 429 right away; a computation past its time limit ends with 422."""

    global _total
    key = user.get("id")
    with _lock:
        if _running.get(key, 0) >= per_user():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="你有一个计算正在进行，请等它完成后再开始新的计算。")
        if _total >= slots():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="服务器正忙：同时进行的计算已经满了，请过一会儿再试。")
        _running[key] = _running.get(key, 0) + 1
        _total += 1
    limit = timeout_seconds()
    try:
        with deadline.limit(limit):
            yield
    except ComputationTimeout:
        minutes = max(1, round(limit / 60))
        raise HTTPException(status_code=422,
                            detail=f"计算超过了 {minutes} 分钟，已经停止。请缩小股票范围或日期区间后再试。") from None
    finally:
        with _lock:
            _running[key] -= 1
            if not _running[key]:
                del _running[key]
            _total -= 1


# --------------------------------------------------------------------------- #
# 结果复用
# --------------------------------------------------------------------------- #

_cache: OrderedDict[str, str] = OrderedDict()
_cache_lock = threading.Lock()


def data_version(root: Path) -> str:
    """Changes whenever any local market-data file is written (each file's path, size and time)."""

    digest = hashlib.sha256()
    for path in sorted(Path(root).rglob("*.parquet")):
        stat = path.stat()
        digest.update(f"{path.relative_to(root)}|{stat.st_size}|{stat.st_mtime_ns};".encode())
    return digest.hexdigest()


def cached(kind: str, user: dict[str, Any], request: Any, root: Path, compute: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """``compute()`` under a slot, or the stored result of the same request on the same data.

    ``request`` must describe everything the result depends on besides the data (it is hashed
    as JSON). Results are kept as JSON text, so a caller can never change a stored one."""

    key = hashlib.sha256(json.dumps([kind, user.get("id"), request, data_version(root)],
                                    ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    with _cache_lock:
        stored = _cache.get(key)
        if stored is not None:
            _cache.move_to_end(key)
            return json.loads(stored)
    with computing(user):
        result = compute()
    # 和直接返回时一样先转成 JSON 能表示的类型，命中缓存时得到的内容完全相同。
    text = json.dumps(jsonable_encoder(result), ensure_ascii=False)
    with _cache_lock:
        _cache[key] = text
        _cache.move_to_end(key)
        while len(_cache) > cache_size():
            _cache.popitem(last=False)
    return json.loads(text)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
