"""轻量状态机：节点 + 条件边 + checkpoint + 重试 + trace。

- 节点是 ``(state, ctx) -> None`` 的纯函数，就地修改 state。
- 每个节点执行后写 checkpoint（SQLite）与 JSONL trace。
- 断点恢复：同一 run_id 再次运行时跳过已完成节点。
- 节点失败按 ``node_retries`` 预算重试，耗尽则记录原因并中止。
- 条件边：节点可带 ``condition``，不满足则标记 skipped。
"""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from trading_agents.orchestrator.events import EventBus, NodeEvent
from trading_agents.utils import NodeTrace, TraceWriter, get_logger, utc_now_iso
from trading_agents.utils.trace import to_jsonable

log = get_logger(__name__)

NodeFn = Callable[[Any, Any], None]
CondFn = Callable[[Any], bool]

_CKPT_SCHEMA = """
CREATE TABLE IF NOT EXISTS checkpoints (
    run_id TEXT PRIMARY KEY,
    state_json TEXT NOT NULL,
    completed_nodes TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


@dataclass
class Node:
    name: str
    fn: NodeFn
    condition: CondFn | None = None  # 条件边：返回 False 则跳过


class CheckpointStore:
    """SQLite checkpoint 持久化。"""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute(_CKPT_SCHEMA)
        self._conn.commit()

    def save(self, run_id: str, state: BaseModel, completed: list[str]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO checkpoints VALUES (?,?,?,?)",
            (
                run_id,
                state.model_dump_json(),
                json.dumps(completed),
                dt.datetime.now(dt.UTC).isoformat(),
            ),
        )
        self._conn.commit()

    def load(self, run_id: str) -> tuple[str, list[str]] | None:
        row = self._conn.execute(
            "SELECT state_json, completed_nodes FROM checkpoints WHERE run_id=?", (run_id,)
        ).fetchone()
        if not row:
            return None
        return row[0], json.loads(row[1])

    def clear(self, run_id: str) -> None:
        self._conn.execute("DELETE FROM checkpoints WHERE run_id=?", (run_id,))
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class StateMachine:
    """顺序执行节点序列，支持条件跳过、checkpoint 恢复与逐节点 trace。"""

    def __init__(
        self,
        nodes: list[Node],
        state: BaseModel,
        ctx: Any,
        run_id: str,
        tracer: TraceWriter,
        checkpoint: CheckpointStore | None = None,
        node_retries: int = 1,
        debug: bool = False,
        event_bus: EventBus | None = None,
    ) -> None:
        self.nodes = nodes
        self.state = state
        self.ctx = ctx
        self.run_id = run_id
        self.tracer = tracer
        self.checkpoint = checkpoint
        self.node_retries = max(1, node_retries)
        self.debug = debug
        self.event_bus = event_bus
        self.completed: list[str] = []

    def restore(self, state_type: type[BaseModel]) -> bool:
        """从 checkpoint 恢复状态与已完成节点列表。返回是否命中。"""
        if not self.checkpoint:
            return False
        saved = self.checkpoint.load(self.run_id)
        if not saved:
            return False
        state_json, completed = saved
        self.state = state_type.model_validate_json(state_json)
        self.completed = list(completed)
        log.info("run %s 从 checkpoint 恢复，跳过节点: %s", self.run_id, self.completed)
        return True

    def run(self) -> BaseModel:
        """执行流水线；节点异常重试耗尽后记录原因并中止（抛错）。"""
        for node in self.nodes:
            if node.name in self.completed:
                if self.debug:
                    log.info("[debug] 跳过已完成节点 %s", node.name)
                # 恢复场景：仍广播 finished 事件，让 UI（TUI）能渲染已完成节点的产出
                self._emit(node.name, "finished", "ok", 0.0)
                continue
            self._run_node(node)
            self.completed.append(node.name)
            if self.checkpoint:
                self.checkpoint.save(self.run_id, self.state, self.completed)
        return self.state

    def _emit(self, node: str, kind: str, status: str = "", duration_ms: float = 0.0,
              error: str = "") -> None:
        """向事件总线广播节点事件（新增订阅通道，trace 逻辑不变）。"""
        if self.event_bus is None:
            return
        artifacts = list(getattr(self.state, "artifacts", []) or [])
        self.event_bus.emit(
            NodeEvent(
                run_id=self.run_id, node=node, kind=kind, status=status,
                duration_ms=round(duration_ms, 2), summary=status or kind,
                artifacts=artifacts, error=error,
            ),
            self.state,
        )

    def _run_node(self, node: Node) -> None:
        started = utc_now_iso()
        t0 = time.perf_counter()
        tokens_before = self._token_sum()
        input_snap = to_jsonable(self.state)
        status, error = "ok", ""
        self._emit(node.name, "started")
        try:
            if node.condition is not None and not node.condition(self.state):
                status = "skipped"
            else:
                last_exc: Exception | None = None
                for attempt in range(1, self.node_retries + 1):
                    try:
                        node.fn(self.state, self.ctx)
                        last_exc = None
                        break
                    except Exception as exc:  # noqa: BLE001 - 记录并重试/中止
                        last_exc = exc
                        log.warning("节点 %s 第 %d 次尝试失败: %s", node.name, attempt, exc)
                if last_exc is not None:
                    raise last_exc
        except Exception as exc:  # noqa: BLE001
            status, error = "error", f"{type(exc).__name__}: {exc}"
            duration = (time.perf_counter() - t0) * 1000
            self._trace(node.name, started, duration, status, input_snap, tokens_before, error)
            self._emit(node.name, "finished", status, duration, error)
            raise RuntimeError(
                f"node {node.name!r} failed after {self.node_retries} attempt(s): {error}"
            ) from exc
        duration = (time.perf_counter() - t0) * 1000
        self._trace(node.name, started, duration, status, input_snap, tokens_before, error)
        self._emit(node.name, "finished", status, duration)
        if self.debug:
            log.info("[debug] 节点 %s 完成（%s, %.1fms）", node.name, status, duration)

    # ------------------------------------------------------------------ #
    def _token_sum(self) -> tuple[int, int]:
        ledger = getattr(self.ctx, "token_ledger", None)
        if ledger is None:
            return 0, 0
        return ledger.prompt_tokens, ledger.completion_tokens

    def _trace(
        self,
        name: str,
        started: str,
        duration_ms: float,
        status: str,
        input_snap: dict,
        tokens_before: tuple[int, int],
        error: str,
    ) -> None:
        p_after, c_after = self._token_sum()
        model = getattr(getattr(self.ctx, "llm", None), "model", "")
        self.tracer.write(
            NodeTrace(
                run_id=self.run_id,
                node=name,
                started_at=started,
                duration_ms=round(duration_ms, 2),
                status=status,
                input_snapshot=input_snap,
                output_snapshot=to_jsonable(self.state),
                model=model,
                prompt_tokens=p_after - tokens_before[0],
                completion_tokens=c_after - tokens_before[1],
                error=error,
            )
        )
