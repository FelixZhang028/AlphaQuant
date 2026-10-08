"""Jev 决策模型客户端（System One / TypeSafe）。

封装 Choice / Noul / Score 三种结构化决策原语，无 API Key 时自动回退到
确定性 mock 模式，保证功能可演示。
"""
from .models import (
    ChoiceRequest,
    ChoiceResponse,
    NoulRequest,
    NoulResponse,
    ScoreRequest,
    ScoreResponse,
)
from .client import JevClient

__all__ = [
    "ChoiceRequest",
    "ChoiceResponse",
    "NoulRequest",
    "NoulResponse",
    "ScoreRequest",
    "ScoreResponse",
    "JevClient",
]
