"""Jev 决策模型客户端（System One / TypeSafe）。

封装 Choice / Noul / Score 三种结构化决策原语；一次请求可以问多个问题（``JevClient.ask``）。
没有 API Key 时不提供演示结果。
"""
from .models import (
    ChoiceRequest,
    ChoiceResponse,
    NoulRequest,
    NoulResponse,
    ScoreRequest,
    ScoreResponse,
)
from .client import JevClient, choice_question, noul_question, score_question

__all__ = [
    "ChoiceRequest",
    "ChoiceResponse",
    "NoulRequest",
    "NoulResponse",
    "ScoreRequest",
    "ScoreResponse",
    "JevClient",
    "choice_question",
    "noul_question",
    "score_question",
]
