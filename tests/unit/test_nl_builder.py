"""自然语言建策略（nl_builder）的单元测试：使用假的 LLM 客户端，不访问网络。"""

from __future__ import annotations

import json

import pytest

from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.nl_builder import (
    NLStrategyBuilder,
    definition_explanation,
)
from trading_agents.llm.base import LLMClient, LLMResponse, Message

VALID_DRAFT = {
    "strategy_id": "ma_volume_breakout",
    "name": "均线放量突破",
    "description": "5日均线上穿20日均线且放量时买入",
    "entry_logic": "all",
    "entry_rules": [
        {
            "left": {"name": "moving_average", "window": 5},
            "operator": "greater_than",
            "right": {"name": "moving_average", "window": 20},
        },
        {
            "left": {"name": "average_amount", "window": 5},
            "operator": "greater_than",
            "value": 20_000_000,
        },
    ],
    "ranking": {
        "indicator": {"name": "return", "window": 20},
        "direction": "descending",
    },
}


class _FakeLLM(LLMClient):
    """按队列返回预设文本的假 LLM。"""

    name = "fake"

    def __init__(self, replies: list[str]) -> None:
        self.replies = list(replies)
        self.calls = 0

    def chat(
        self,
        messages: list[Message],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        self.calls += 1
        text = self.replies.pop(0) if self.replies else "{}"
        return LLMResponse(text=text, model="fake")


def test_generate_valid_definition_in_one_shot() -> None:
    client = _FakeLLM([json.dumps(VALID_DRAFT, ensure_ascii=False)])
    definition = NLStrategyBuilder(client).generate("5日均线高于20日均线并且放量时买入")
    assert definition.strategy_id == "ma_volume_breakout"
    assert len(definition.entry_rules) == 2
    assert definition.minimum_history_days >= 21
    assert client.calls == 1


def test_generate_repairs_once_after_invalid_output() -> None:
    client = _FakeLLM(["这不是JSON", json.dumps(VALID_DRAFT, ensure_ascii=False)])
    definition = NLStrategyBuilder(client).generate("均线突破")
    assert definition.name == "均线放量突破"
    assert client.calls == 2


def test_generate_fails_after_exhausting_attempts() -> None:
    client = _FakeLLM(["{}", "{}"])
    with pytest.raises(ConfigurationError, match="未通过校验"):
        NLStrategyBuilder(client, max_attempts=2).generate("随便")


def test_generate_rejects_schema_violation() -> None:
    bad = {**VALID_DRAFT, "entry_rules": []}
    client = _FakeLLM([json.dumps(bad), json.dumps(bad)])
    with pytest.raises(ConfigurationError):
        NLStrategyBuilder(client).generate("没有条件的策略")


def test_generate_rejects_empty_description() -> None:
    client = _FakeLLM([])
    with pytest.raises(ConfigurationError, match="策略描述"):
        NLStrategyBuilder(client).generate("   ")


def test_definition_explanation_is_chinese_and_complete() -> None:
    client = _FakeLLM([json.dumps(VALID_DRAFT, ensure_ascii=False)])
    definition = NLStrategyBuilder(client).generate("均线突破")
    text = definition_explanation(definition, top_n=5, rebalance="weekly")
    assert "均线放量突破" in text
    assert "5日移动平均线" in text
    assert "每周调仓" in text
    assert "前5只" in text
