"""OpenRouter Decisions adapter. Only unconfigured clients use demo results."""
from __future__ import annotations
import math
from typing import Any
import requests
from .mock import mock_choice, mock_noul, mock_score
from .models import ChoiceRequest, ChoiceResponse, NoulRequest, NoulResponse, ScoreRequest, ScoreResponse

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_TIMEOUT = 30.0

def probability(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid probability")
    return value

class JevClient:
    def __init__(self, api_key=None, base_url=OPENROUTER_DECISIONS_URL,
                 timeout=DEFAULT_TIMEOUT, model="typesafe/jev-1.13"):
        self.api_key, self.base_url, self.timeout, self.model = api_key, base_url, timeout, model

    @property
    def has_key(self):
        return bool(self.api_key)

    def _decide(self, question, state):
        data = self._post({"model": self.model, "state": state, "questions": {"decision": question}})
        answer = data.get("answers", {}).get("decision")
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            raise ValueError("Invalid Decisions response")
        return answer

    def choice(self, req: ChoiceRequest) -> ChoiceResponse:
        if not self.has_key:
            return mock_choice(req)
        answer = self._decide({"type": "choice", "instructions": req.question,
                               "criteria": {opt: opt for opt in req.options}}, req.state)
        selected = answer["choice"]
        if selected not in req.options:
            raise ValueError("Unknown decision option")
        probs = {opt: probability(answer["probabilities"][opt]) for opt in req.options}
        self._check_distribution(probs)
        return ChoiceResponse(selected, probs, probability(answer["confidence"]), mock=False)

    def noul(self, req: NoulRequest) -> NoulResponse:
        if not self.has_key:
            return mock_noul(req)
        answer = self._decide({"type": "noul", "instructions": req.condition}, req.state)
        prob = probability(answer["noul"])
        # Noul has no separate confidence field in the provider schema.
        return NoulResponse(prob, None, mock=False)

    def score(self, req: ScoreRequest) -> ScoreResponse:
        if not self.has_key:
            return mock_score(req)
        answer = self._decide({"type": "score", "instructions": req.question,
                               "criteria": req.levels}, req.state)
        value = float(answer["score"])
        if not math.isfinite(value) or not 0 <= value <= len(req.levels) - 1:
            raise ValueError("Invalid score")
        probs = {label: probability(answer["probabilities"][str(i)]) for i, label in enumerate(req.levels)}
        self._check_distribution(probs)
        return ScoreResponse(value, probs, probability(answer["confidence"]), req.levels, mock=False)

    @staticmethod
    def _check_distribution(probs):
        if abs(sum(probs.values()) - 1) > 0.02:
            raise ValueError("Invalid probability distribution")

    def _post(self, payload: dict[str, Any]):
        with requests.post(self.base_url, json=payload,
                           headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                           timeout=self.timeout) as resp:
            resp.raise_for_status()
            return resp.json()
