"""自然语言建策略：把中文策略描述转换为平台结构化规则（RuleStrategyDefinition）。

流程（对应反馈第 3 条）：

1. 用户输入自然语言描述，如「5日均线高于20日均线并且放量时买入」；
2. 大模型把描述转换为符合平台规则的 JSON（指标、比较符、排序均在白名单内）；
3. 平台用 ``RuleStrategyDefinition`` 强校验，并生成中文解释供用户确认；
4. 校验失败时把错误信息回喂给模型自动修复一次，仍失败则明确报错，
   用户可改用模板或积木编辑器。

模型支持：任何 OpenAI 兼容端点（DeepSeek / Kimi / Ollama 本地等），
由 ``trading_agents.llm.base.create_llm_client`` 统一构造。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from quant_platform.core.exceptions import ConfigurationError
from quant_platform.strategies.rule_schema import (
    INDICATOR_LABELS,
    OPERATOR_LABELS,
    RuleStrategyDefinition,
)
from trading_agents.llm.base import LLMClient, Message, StructuredOutputError

# ---------------------------------------------------------------- 提示词 ----

_INDICATOR_DOC = "\n".join(
    f"- {name}: {label}" for name, label in INDICATOR_LABELS.items()
)
_OPERATOR_DOC = "\n".join(
    f"- {name}: {label}" for name, label in OPERATOR_LABELS.items()
)

SYSTEM_PROMPT = f"""你是量化策略助手。把用户的中文策略描述转换为严格符合以下协议的 JSON 对象。

协议字段：
- strategy_id: 英文小写标识，只能用字母数字下划线，如 "ma_volume_breakout"
- name: 中文策略名，不超过80字
- description: 一句话中文说明
- entry_logic: "all"（全部条件同时满足）或 "any"（任一满足）
- entry_rules: 1至10条买入条件，每条形如：
  {{"left": {{"name": 指标, "window": 周期}}, "operator": 比较符, "value": 数值}}
  或右侧为另一指标：
  {{"left": {{"name": 指标, "window": 周期}}, "operator": 比较符,
   "right": {{"name": 指标, "window": 周期}}}}
- ranking: {{"indicator": {{"name": 指标, "window": 周期}},
            "direction": "descending" 或 "ascending"}}

允许的指标（name 必须逐字使用，close 不需要 window，其余必须有整数 window）：
{_INDICATOR_DOC}

允许的比较符（operator 必须逐字使用）：
{_OPERATOR_DOC}

规则：
- 涨跌幅、回撤类阈值用小数，例如 5% 写成 0.05；
- 平均成交额用元为单位，例如 2000 万写成 20000000；
- 「A大于B」即 left=A, operator=greater_than, right=B；
- 只输出 JSON 对象本身，不要输出任何解释或代码块标记。"""

REPAIR_PROMPT = """上一次生成的 JSON 未通过平台校验，错误信息：
{error}

请修正后重新只输出符合协议的 JSON 对象。"""


# ------------------------------------------------------------ 结构化模型 ----


class _NLIndicator(BaseModel):
    name: str
    window: int | None = None


class _NLRule(BaseModel):
    left: _NLIndicator
    operator: str
    value: float | None = None
    right: _NLIndicator | None = None


class _NLRanking(BaseModel):
    indicator: _NLIndicator
    direction: str = "descending"


class NLStrategyDraft(BaseModel):
    """LLM 输出的策略草稿，随后交由 RuleStrategyDefinition 做权威校验。"""

    strategy_id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    entry_logic: str = "all"
    entry_rules: list[_NLRule] = Field(min_length=1, max_length=10)
    ranking: _NLRanking

    def to_mapping(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "description": self.description,
            "entry_logic": self.entry_logic,
            "entry_rules": [
                rule.model_dump(exclude_none=True) for rule in self.entry_rules
            ],
            "ranking": self.ranking.model_dump(exclude_none=True),
        }


# ---------------------------------------------------------------- 生成器 ----


class NLStrategyBuilder:
    """自然语言 -> 结构化策略规则。不执行模型输出的任何代码。"""

    def __init__(self, client: LLMClient, *, max_attempts: int = 2) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必须 >= 1")
        self.client = client
        self.max_attempts = max_attempts

    def generate(self, description: str) -> RuleStrategyDefinition:
        """生成并通过平台校验的策略定义；失败抛 ConfigurationError。"""

        text = description.strip()
        if not text:
            raise ConfigurationError("请输入策略描述")

        messages: list[Message] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"策略描述：{text}"},
        ]
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            if attempt > 0 and last_error is not None:
                messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": REPAIR_PROMPT.format(error=last_error),
                    },
                ]
            try:
                draft, _ = self.client.chat_structured(
                    messages, NLStrategyDraft, temperature=0.1, max_tokens=2048
                )
                assert isinstance(draft, NLStrategyDraft)
                return RuleStrategyDefinition.from_mapping(draft.to_mapping())
            except (StructuredOutputError, ConfigurationError) as exc:
                last_error = exc
        raise ConfigurationError(
            f"模型生成的策略规则未通过校验（已自动重试 {self.max_attempts} 次）："
            f"{last_error}。请换一种更具体的描述，或改用模板 / 积木编辑器。"
        ) from last_error


def definition_explanation(
    definition: RuleStrategyDefinition, *, top_n: int, rebalance: str
) -> str:
    """生成给用户确认的中文解释（结构 + 白话执行方式）。"""

    lines = [f"策略名称：{definition.name}"]
    if definition.description:
        lines.append(f"策略说明：{definition.description}")
    logic = "同时满足" if definition.entry_logic == "all" else "满足任一"
    lines.append(f"买入条件（{logic}）：")
    for index, rule in enumerate(definition.entry_rules, start=1):
        lines.append(f"  {index}. {rule.describe()}")
    lines.append(f"选股排序：{definition.ranking.describe()}")
    lines.append(f"执行方式：{definition.describe(top_n=top_n, rebalance=rebalance)}")
    lines.append(f"所需历史：至少 {definition.minimum_history_days} 个交易日")
    return "\n".join(lines)
