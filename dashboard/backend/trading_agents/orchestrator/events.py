"""节点事件机制：状态机在每节点开始/完成时向订阅者发事件。

事件只是新增的订阅通道；JSONL trace 逻辑不变。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field


class NodeEvent(BaseModel):
    """单节点生命周期事件。"""

    run_id: str
    node: str
    kind: str  # started / finished
    status: str = ""  # finished 时: ok / skipped / error
    duration_ms: float = 0.0
    summary: str = ""
    artifacts: list[str] = Field(default_factory=list)
    error: str = ""


EventListener = Callable[[NodeEvent, Any], None]  # (事件, 当前流水线状态)

# Agent 级进度回调：(agent 名, 状态 in_progress/completed, 产出对象或 None)
AgentReporter = Callable[[str, str, Any], None]


class EventBus:
    """极简同步事件总线：订阅者按注册顺序同步收到事件。

    订阅者异常不阻塞流水线（打印日志后跳过），避免 UI 层拖垮编排层。
    """

    def __init__(self) -> None:
        self._listeners: list[EventListener] = []

    def subscribe(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def emit(self, event: NodeEvent, state: Any = None) -> None:
        from trading_agents.utils import get_logger

        for listener in self._listeners:
            try:
                listener(event, state)
            except Exception as exc:  # noqa: BLE001 - 订阅者故障不阻塞流水线
                get_logger(__name__).warning("event listener error: %s", exc)
