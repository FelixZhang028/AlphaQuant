"""Jev 决策数据模型：Choice / Noul / Score。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------- Choice: 在给定选项中选择 ----------------

@dataclass
class ChoiceRequest:
    question: str
    options: list[str]
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChoiceResponse:
    selected: str
    probabilities: dict[str, float]  # option -> probability, sum == 1
    confidence: float  # 0-1
    mock: bool = False


# ---------------- Noul: 条件是否成立 ----------------

@dataclass
class NoulRequest:
    condition: str
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class NoulResponse:
    probability: float  # 0-1, P(condition is true)
    confidence: float | None
    mock: bool = False


# ---------------- Score: 在有序量表上的位置 ----------------

@dataclass
class ScoreRequest:
    question: str
    levels: list[str]  # 有序等级列表，如 ["低", "中", "高"]
    state: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoreResponse:
    score: float  # 加权分数，范围 [0, len(levels)-1]
    level_probabilities: dict[str, float]  # level -> probability
    confidence: float
    levels: list[str] = field(default_factory=list)  # 有序等级列表
    mock: bool = False

    def to_score_0_100(self) -> float:
        """将 score 映射到 0-100 分。"""
        n = len(self.levels) if self.levels else len(self.level_probabilities)
        if n <= 1:
            return 50.0
        return round(self.score / (n - 1) * 100, 1)
