"""A time limit for one computation, checked at safe points in long loops.

The web layer sets a deadline before a heavy request (a backtest, a factor evaluation) and long
loops call :func:`check` (the backtest engine once per trading day, the evaluator after each
factor). Nothing is interrupted in the middle of a step, so data is never left half written;
a run stops at most one step after its time is up.

:class:`ComputationTimeout` derives from ``BaseException`` on purpose: library code that catches
``Exception`` to skip one bad item (a factor that fails, a day without data) must not swallow the
stop and carry on.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_DEADLINE: ContextVar[float | None] = ContextVar("computation_deadline", default=None)


class ComputationTimeout(BaseException):
    """The computation ran past its time limit."""


def check() -> None:
    """Raise :class:`ComputationTimeout` when the current computation is past its deadline."""

    deadline = _DEADLINE.get()
    if deadline is not None and time.monotonic() > deadline:
        raise ComputationTimeout("计算超过了时间限制")


@contextmanager
def limit(seconds: float | None) -> Iterator[None]:
    """Run the block with a deadline ``seconds`` from now (no limit when ``None``)."""

    token = _DEADLINE.set(None if seconds is None else time.monotonic() + seconds)
    try:
        yield
    finally:
        _DEADLINE.reset(token)
