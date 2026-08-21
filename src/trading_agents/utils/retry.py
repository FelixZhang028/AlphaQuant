"""带预算的重试工具。重试耗尽抛 :class:`RetryExhaustedError`，绝不静默吞异常。"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


class RetryExhaustedError(RuntimeError):
    """重试预算耗尽。``cause`` 为最后一次异常。"""


def retry(
    fn: Callable[[], T],
    max_attempts: int,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    backoff_seconds: float = 0.0,
) -> T:
    """最多尝试 ``max_attempts`` 次调用 ``fn``，全部失败则抛 RetryExhaustedError。"""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except exceptions as exc:  # noqa: BLE001 - 由调用方限定异常类型
            last = exc
            if attempt < max_attempts and backoff_seconds > 0:
                time.sleep(backoff_seconds)
    raise RetryExhaustedError(f"retry exhausted after {max_attempts} attempts: {last}") from last
