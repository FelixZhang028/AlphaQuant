"""OpenRouter Decisions API (Jev): typed questions about one state, answered with probabilities.

One request carries a ``state`` and any number of named questions; they are answered
independently and the price depends only on the input, so related questions share one request.
Question shapes follow the API reference:

- choice: ``instructions`` and ``criteria`` = {option: what it means}; answer ``choice``,
  ``confidence`` and ``probabilities`` by option.
- noul: ``instructions`` and ``criteria`` = {"true": ..., "false": ...}; answer ``noul``, the
  probability of true.
- score: ``instructions`` and ``criteria`` = ordered levels; answer ``score`` (0 .. levels-1),
  ``confidence`` and ``probabilities`` by level index.

There is no demo mode: without a key there is no client (see ``app.quant.platform_ai``), so no
made-up probability is ever shown as if a model had answered.
"""
from __future__ import annotations

import math
from typing import Any

import requests

from .models import ChoiceRequest, ChoiceResponse, NoulRequest, NoulResponse, ScoreRequest, ScoreResponse

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_MODEL = "typesafe/jev-1.13"
DEFAULT_TIMEOUT = 30.0


def probability(value: Any) -> float:
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid probability")
    return value


def _check_distribution(probs: dict[str, float]) -> None:
    if abs(sum(probs.values()) - 1) > 0.02:
        raise ValueError("Invalid probability distribution")


def choice_question(instructions: str, criteria: dict[str, str]) -> dict[str, Any]:
    return {"type": "choice", "instructions": instructions, "criteria": dict(criteria)}


def noul_question(instructions: str, true_means: str, false_means: str) -> dict[str, Any]:
    return {"type": "noul", "instructions": instructions, "criteria": {"true": true_means, "false": false_means}}


def score_question(instructions: str, levels: list[str]) -> dict[str, Any]:
    return {"type": "score", "instructions": instructions, "criteria": list(levels)}


def parse_answer(question: dict[str, Any], answer: Any) -> dict[str, Any]:
    """One answer, checked against its question; raises ValueError for anything malformed."""

    if not isinstance(answer, dict) or answer.get("type") != question["type"]:
        raise ValueError("Invalid Decisions response")
    if question["type"] == "choice":
        options = list(question["criteria"])
        if answer.get("choice") not in options:
            raise ValueError("Unknown decision option")
        probs = {option: probability(answer["probabilities"][option]) for option in options}
        _check_distribution(probs)
        return {"type": "choice", "choice": answer["choice"], "probabilities": probs, "confidence": probability(answer["confidence"])}
    if question["type"] == "noul":
        return {"type": "noul", "probability": probability(answer["noul"])}
    levels = list(question["criteria"])
    score = float(answer["score"])
    if not math.isfinite(score) or not 0 <= score <= len(levels) - 1:
        raise ValueError("Invalid score")
    probs = {level: probability(answer["probabilities"][str(i)]) for i, level in enumerate(levels)}
    _check_distribution(probs)
    return {"type": "score", "score": score, "probabilities": probs, "confidence": probability(answer["confidence"])}


class JevClient:
    def __init__(self, api_key: str, base_url: str = OPENROUTER_DECISIONS_URL,
                 timeout: float = DEFAULT_TIMEOUT, model: str = DEFAULT_MODEL):
        if not api_key:
            raise ValueError("Jev 需要 OpenRouter API Key")
        self.api_key, self.base_url, self.timeout, self.model = api_key, base_url, timeout, model

    def ask(self, state: Any, questions: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Answer all ``questions`` about ``state`` in one request, keyed like ``questions``."""

        data = self._post({"model": self.model, "state": state, "questions": questions})
        answers = data.get("answers") if isinstance(data, dict) else None
        if not isinstance(answers, dict):
            raise ValueError("Invalid Decisions response")
        return {name: parse_answer(question, answers.get(name)) for name, question in questions.items()}

    def choice(self, req: ChoiceRequest) -> ChoiceResponse:
        answer = self.ask(req.state, {"decision": choice_question(req.question, {opt: opt for opt in req.options})})["decision"]
        return ChoiceResponse(answer["choice"], answer["probabilities"], answer["confidence"])

    def noul(self, req: NoulRequest) -> NoulResponse:
        question = noul_question(req.condition, req.true_means, req.false_means)
        return NoulResponse(self.ask(req.state, {"decision": question})["decision"]["probability"])

    def score(self, req: ScoreRequest) -> ScoreResponse:
        answer = self.ask(req.state, {"decision": score_question(req.question, req.levels)})["decision"]
        return ScoreResponse(answer["score"], answer["probabilities"], answer["confidence"], req.levels)

    def _post(self, payload: dict[str, Any]):
        with requests.post(self.base_url, json=payload,
                           headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                           timeout=self.timeout) as resp:
            resp.raise_for_status()
            return resp.json()
