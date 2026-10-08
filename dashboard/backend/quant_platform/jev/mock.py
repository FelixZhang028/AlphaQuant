"""Jev 确定性 mock 决策。

基于输入内容的哈希生成可复现的决策结果，无需 API Key 即可演示。
"""
from __future__ import annotations

import hashlib
from typing import Any

from .models import (
    ChoiceRequest,
    ChoiceResponse,
    NoulRequest,
    NoulResponse,
    ScoreRequest,
    ScoreResponse,
)


def _seed(*parts: Any) -> int:
    """将任意输入转为确定性整数种子。"""
    text = "|".join(str(p) for p in parts)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _normalize(values: list[float]) -> list[float]:
    total = sum(values)
    if total <= 0:
        n = len(values)
        return [1.0 / n] * n
    return [v / total for v in values]


def mock_choice(req: ChoiceRequest) -> ChoiceResponse:
    """确定性 mock Choice：基于问题和选项哈希选择。"""
    options = req.options or ["A", "B"]
    seed = _seed(req.question, *options)
    # 为每个选项生成一个权重
    weights = []
    for i, opt in enumerate(options):
        w = ((seed >> (i * 4)) & 0xFF) + 1  # 1-256
        weights.append(float(w))
    probs = _normalize(weights)
    # 选概率最大的
    max_idx = max(range(len(options)), key=lambda i: probs[i])
    return ChoiceResponse(
        selected=options[max_idx],
        probabilities={opt: round(p, 4) for opt, p in zip(options, probs)},
        confidence=round(max(probs), 4),
        mock=True,
    )


def mock_noul(req: NoulRequest) -> NoulResponse:
    """确定性 mock Noul：基于条件哈希生成概率。"""
    seed = _seed(req.condition)
    prob = (seed % 1000) / 1000.0  # 0-1
    confidence = 0.5 + ((seed >> 10) % 500) / 1000.0  # 0.5-1.0
    return NoulResponse(
        probability=round(prob, 4),
        confidence=round(min(confidence, 1.0), 4),
        mock=True,
    )


def mock_score(req: ScoreRequest) -> ScoreResponse:
    """确定性 mock Score：基于问题和等级哈希生成分数。"""
    levels = req.levels or ["低", "中", "高"]
    n = len(levels)
    seed = _seed(req.question, *levels)
    # 为每个等级生成权重
    weights = []
    for i in range(n):
        w = ((seed >> (i * 5)) & 0xFF) + 1
        weights.append(float(w))
    probs = _normalize(weights)
    # 加权分数 = sum(prob[i] * i)
    score = sum(p * i for i, p in enumerate(probs))
    confidence = 0.5 + ((seed >> 12) % 500) / 1000.0
    return ScoreResponse(
        score=round(score, 4),
        level_probabilities={lv: round(p, 4) for lv, p in zip(levels, probs)},
        confidence=round(min(confidence, 1.0), 4),
        levels=levels,
        mock=True,
    )
