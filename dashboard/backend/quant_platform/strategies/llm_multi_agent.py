"""LLM 多智能体决策策略：用 trading_agents 流水线替代规则打分。

对流动性预筛后的候选标的逐个调用 LLM 多智能体决策流水线
（分析师团队 -> 多空辩论 -> 交易员提案 -> 风控 -> 组合经理审批），
将批准的买入决策映射为带显式目标权重的信号。

注意：非 mock 的 LLM provider 会产生真实 API 调用，回测成本高且结果
不可复现；建议仅在小 universe、少调仓频率下使用，并开启缓存。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, ClassVar

import pandas as pd

from quant_platform.agents_bridge import AgentRunner, decision_to_signal
from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyParameter

log = logging.getLogger(__name__)

_LLM_PROVIDER_CHOICES = (
    "mock", "kimi", "openai", "deepseek", "qwen", "glm", "ollama", "custom"
)


@dataclass(frozen=True)
class LLMMultiAgentParameters:
    """LLM 多智能体策略的可配置参数。"""

    llm_provider: str = "mock"
    debate_rounds: int = 1
    lookback_days: int = 60
    max_candidates: int = 10
    max_weight_per_stock: float = 0.2
    use_cache: bool = True
    custom_base_url: str = ""
    custom_model: str = ""


class LLMMultiAgentStrategy(Strategy):
    """每个调仓日对候选股票调用 LLM 多智能体流水线生成买入信号。"""

    plugin_name = "llm_multi_agent"
    display_name = "LLM 多智能体决策"
    description = "对流动性预筛后的候选标的调用 LLM 多智能体流水线，买入获批准的标的。"
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "llm_provider",
            "LLM Provider",
            ParameterKind.STRING,
            "mock",
            "mock 离线确定；其他 provider 需配置 API key；custom 用于自定义端点",
            choices=_LLM_PROVIDER_CHOICES,
        ),
        StrategyParameter(
            "debate_rounds",
            "辩论轮数",
            ParameterKind.INTEGER,
            1,
            "多空辩论轮数，越多越慢越贵",
            minimum=0,
            maximum=4,
        ),
        StrategyParameter(
            "lookback_days",
            "行情回看天数",
            ParameterKind.INTEGER,
            60,
            "喂给智能体的日线窗口长度",
            minimum=20,
            maximum=250,
        ),
        StrategyParameter(
            "max_candidates",
            "最大候选数",
            ParameterKind.INTEGER,
            10,
            "按最近20日平均成交额预筛后的候选标的数量上限",
            minimum=1,
            maximum=50,
        ),
        StrategyParameter(
            "max_weight_per_stock",
            "单票权重上限",
            ParameterKind.NUMBER,
            0.2,
            "单个标的的目标仓位占组合比例上限",
            minimum=0.01,
            maximum=1.0,
        ),
        StrategyParameter(
            "use_cache",
            "启用决策缓存",
            ParameterKind.BOOLEAN,
            True,
            "缓存 LLM 决策到磁盘，重复回测不重复调用",
        ),
        StrategyParameter(
            "custom_base_url",
            "自定义 Base URL",
            ParameterKind.STRING,
            "",
            "选择 custom 时必填：OpenAI 兼容端点地址，如 https://api.example.com/v1",
        ),
        StrategyParameter(
            "custom_model",
            "自定义模型名",
            ParameterKind.STRING,
            "",
            "选择 custom 时必填：该端点支持的模型名称",
        ),
    )
    required_fields = frozenset(
        {"symbol", "trade_date", "raw_open", "raw_high", "raw_low", "raw_close",
         "volume", "amount"}
    )

    def __init__(self, strategy_id: str, parameters: LLMMultiAgentParameters) -> None:
        self.strategy_id = strategy_id
        self.config = parameters
        self._runner = AgentRunner(
            llm_provider=parameters.llm_provider,
            debate_rounds=parameters.debate_rounds,
            use_cache=parameters.use_cache,
            base_url=parameters.custom_base_url or None,
            model=parameters.custom_model or None,
        )

    @classmethod
    def from_parameters(
        cls, strategy_id: str, parameters: dict[str, Any]
    ) -> LLMMultiAgentStrategy:
        """Build the strategy from catalog-validated values."""

        return cls(
            strategy_id,
            LLMMultiAgentParameters(
                llm_provider=str(parameters["llm_provider"]),
                debate_rounds=int(parameters["debate_rounds"]),
                lookback_days=int(parameters["lookback_days"]),
                max_candidates=int(parameters["max_candidates"]),
                max_weight_per_stock=float(parameters["max_weight_per_stock"]),
                use_cache=bool(parameters["use_cache"]),
                custom_base_url=str(parameters.get("custom_base_url", "")),
                custom_model=str(parameters.get("custom_model", "")),
            ),
        )

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """预筛候选标的并逐个调用 LLM 决策流水线。"""

        context.require_fields(self.required_fields)
        history = context.history(
            fields=["raw_open", "raw_high", "raw_low", "raw_close", "volume", "amount"],
            lookback=self.config.lookback_days,
        )
        signals: list[Signal] = []
        for symbol in self._select_candidates(history):
            frame = history[history["symbol"] == symbol]
            try:
                decision = self._runner.decide(symbol, context.trade_date, frame)
            except Exception as exc:  # noqa: BLE001 - 单票失败不中断整个回测
                log.warning("LLM 决策失败 %s @ %s: %s", symbol, context.trade_date, exc)
                continue
            signal = decision_to_signal(
                decision,
                self.strategy_id,
                context.trade_date,
                symbol,
                self.config.max_weight_per_stock,
            )
            if signal is not None:
                signals.append(signal)
        return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))

    def _select_candidates(self, history: pd.DataFrame) -> list[str]:
        """按最近 20 日平均成交额取 top max_candidates。"""
        recent = history.groupby("symbol", observed=True, group_keys=False).tail(20)
        average_amount = (
            pd.to_numeric(recent["amount"], errors="coerce").groupby(recent["symbol"]).mean()
        )
        top = average_amount.sort_values(ascending=False).head(self.config.max_candidates)
        return [str(symbol) for symbol in top.index]
