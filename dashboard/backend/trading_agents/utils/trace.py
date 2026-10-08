"""JSONL 运行 trace：每节点的输入/输出快照、耗时、模型、token 消耗。"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class NodeTrace(BaseModel):
    """单节点 trace 记录。"""

    run_id: str
    node: str
    started_at: str
    duration_ms: float
    status: str  # ok / error / skipped
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    output_snapshot: dict[str, Any] = Field(default_factory=dict)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    error: str = ""


class TraceWriter:
    """把 NodeTrace 追加写入 ``<trace_dir>/<run_id>.jsonl``。"""

    def __init__(self, trace_dir: Path, run_id: str) -> None:
        trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = trace_dir / f"{run_id}.jsonl"

    def write(self, trace: NodeTrace) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(trace.model_dump_json() + "\n")


def utc_now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def to_jsonable(obj: Any) -> Any:
    """把 Pydantic 模型等转成可 JSON 序列化结构，用于 trace 快照。"""
    if isinstance(obj, BaseModel):
        return json.loads(obj.model_dump_json())
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    return obj
