"""编排层：自研轻量状态机（不引入 LangGraph）。

能力：节点定义、条件边、全局状态快照、SQLite checkpoint 断点恢复、
每节点重试预算、debug 逐节点 trace。不承载业务逻辑。
"""

from trading_agents.orchestrator.events import EventBus, NodeEvent
from trading_agents.orchestrator.machine import Node, StateMachine
from trading_agents.orchestrator.pipeline import (
    PipelineContext,
    PipelineState,
    build_pipeline,
    run_pipeline,
)

__all__ = [
    "EventBus",
    "Node",
    "NodeEvent",
    "PipelineContext",
    "PipelineState",
    "StateMachine",
    "build_pipeline",
    "run_pipeline",
]
