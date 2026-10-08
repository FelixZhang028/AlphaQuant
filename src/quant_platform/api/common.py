"""Shared HTTP errors, JSON normalization, pagination and full CSV exports."""

from __future__ import annotations

import json
import math
import re
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from quant_platform.core.diagnostics import redact


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def wire(value: Any) -> Any:
    """Retain dates, units, missing values and Series indexes in strict JSON."""
    if isinstance(value, BaseModel):
        return wire(value.model_dump(mode="json"))
    if isinstance(value, pd.DataFrame):
        return table(value)
    if isinstance(value, pd.Series):
        return {"index": wire(value.index.tolist()), "values": wire(value.tolist())}
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: wire(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {str(key): wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [wire(item) for item in value]
    if value is pd.NA or value is pd.NaT or value is None:
        return None
    if isinstance(value, Enum):
        return wire(value.value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return wire(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def table(frame: pd.DataFrame, offset: int = 0, limit: int | None = None) -> dict:
    selected = frame.iloc[offset : None if limit is None else offset + limit]
    # pandas handles nullable dtypes, numpy values, NaT, NaN and infinity.
    rows = json.loads(selected.to_json(orient="records", date_format="iso", double_precision=15))
    return {
        "columns": list(frame.columns),
        "rows": rows,
        "total": len(frame),
        "offset": offset,
        "limit": limit,
    }


def safe_wire(value: Any) -> Any:
    return redact(wire(value))


def csv_response(frame: pd.DataFrame, filename: str) -> StreamingResponse:
    """Export every filtered row; pagination is deliberately not an argument."""

    def chunks():
        yield b"\xef\xbb\xbf"
        if frame.empty:
            yield frame.to_csv(index=False).encode("utf-8")
        else:
            for start in range(0, len(frame), 10000):
                yield (
                    frame.iloc[start : start + 10000]
                    .to_csv(index=False, header=start == 0)
                    .encode("utf-8")
                )

    return StreamingResponse(
        chunks(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def resource_path(root: Path, identifier: str) -> Path:
    """Only a single resource ID inside the configured root is addressable."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", identifier):
        raise ApiError(422, "invalid_id", "资源编号不合法")
    base = root.resolve()
    path = (base / identifier).resolve()
    if path.parent != base:
        raise ApiError(422, "invalid_id", "资源编号不合法")
    if not path.is_dir():
        raise ApiError(404, "not_found", "资源不存在")
    return path
