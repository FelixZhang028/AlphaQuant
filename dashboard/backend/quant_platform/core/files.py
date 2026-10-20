"""Swapping a file in whole, also on Windows.

Files are written to a temporary next to the target and then renamed over it, so a reader never
sees half a file. On Windows the rename fails with ``PermissionError`` while another process has
the target open — for example the backend reading a data job's ``progress.json`` every few seconds
while the job writes it. That is momentary, so the rename is retried for a while instead of
failing the whole job.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

# Windows 上旧文件正被别的进程读着时不能替换：等它读完，最多等这么久。
REPLACE_WAIT_SECONDS = 10.0
RETRY_SECONDS = 0.05


def replace_file(source: Path | str, target: Path | str, wait: float | None = None) -> None:
    """``os.replace(source, target)``, retried for up to ``wait`` seconds (default
    ``REPLACE_WAIT_SECONDS``) while the target is held open by another process."""

    deadline = time.monotonic() + (REPLACE_WAIT_SECONDS if wait is None else wait)
    while True:
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if time.monotonic() > deadline:
                raise
            time.sleep(RETRY_SECONDS)


def write_json_atomic(path: Path | str, value: Any, **dump: Any) -> None:
    """Write ``value`` as JSON to ``path`` in one rename; the temporary is removed if anything fails."""

    path = Path(path)
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, **dump), encoding="utf-8")
        replace_file(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
