"""因子合成选股策略：把因子库中的因子按权重合成打分，供回测与模拟交易复用。

参数 ``factors_json`` 为 JSON 对象，包含成分因子与预处理配置，例如::

    {
        "components": [{"name": "momentum_20", "weight": 1.0}],
        "preprocess": {"winsorize": true, "fill_method": "drop"}
    }

旧版仅包含成分列表的 JSON 仍可读取，并按“不去极值、剔除缺失”执行。

策略在每个调仓日取足够长度的历史行情，逐因子计算当日截面值，按日
z-score 标准化（含方向调整）后加权求和作为打分，分数越高越优先持有。
全部计算只依赖 ``<= 当日`` 的数据，满足平台的防未来函数约定。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar

import pandas as pd

from quant_platform.core.exceptions import ConfigurationError
from quant_platform.factors.base import FactorDefinition
from quant_platform.factors.combine import combine_factors
from quant_platform.factors.preprocess import FactorPreprocessConfig
from quant_platform.factors.registry import default_registry
from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyParameter


@dataclass(frozen=True)
class FactorWeight:
    """一个成分因子及其权重。"""

    name: str
    weight: float = 1.0


@dataclass(frozen=True)
class FactorCompositeParameters:
    components: tuple[FactorWeight, ...]
    preprocess: FactorPreprocessConfig = field(default_factory=FactorPreprocessConfig)

    @classmethod
    def from_json(cls, text: str) -> FactorCompositeParameters:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigurationError(f"因子组合JSON格式错误：{exc}") from exc
        component_data: object
        if isinstance(raw, list):
            component_data = raw
            preprocess = FactorPreprocessConfig()
        elif isinstance(raw, dict):
            component_data = raw.get("components")
            preprocess_data = raw.get("preprocess")
            if preprocess_data is not None and not isinstance(preprocess_data, dict):
                raise ConfigurationError("因子预处理配置必须是 JSON 对象")
            try:
                preprocess = FactorPreprocessConfig.from_mapping(preprocess_data)
            except ValueError as exc:
                raise ConfigurationError(f"因子预处理配置错误：{exc}") from exc
        else:
            raise ConfigurationError("因子组合必须是 JSON 对象或非空列表")
        if not isinstance(component_data, list) or not component_data:
            raise ConfigurationError("因子组合 components 必须是非空列表")
        components: list[FactorWeight] = []
        registry = default_registry()
        for item in component_data:
            if not isinstance(item, dict) or "name" not in item:
                raise ConfigurationError('因子组合元素必须形如 {"name": ..., "weight": ...}')
            name = str(item["name"]).strip()
            if name not in registry:
                raise ConfigurationError(f"未注册的因子：{name}")
            components.append(FactorWeight(name, float(item.get("weight", 1.0))))
        names = [item.name for item in components]
        if len(set(names)) != len(names):
            raise ConfigurationError("因子组合中存在重复因子")
        return cls(tuple(components), preprocess)

    def to_json(self) -> str:
        return json.dumps(
            {
                "components": [
                    {"name": item.name, "weight": item.weight} for item in self.components
                ],
                "preprocess": self.preprocess.to_dict(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )


class FactorCompositeStrategy(Strategy):
    """按因子库定义合成截面打分；不写死任何单一因子逻辑。"""

    plugin_name = "factor_composite"
    display_name = "因子合成策略"
    description = "由因子研究室生成：多个内置因子按权重合成打分，等权持有高分股票"
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "factors_json",
            "因子组合定义",
            ParameterKind.STRING,
            "[]",
            'JSON 对象，包含 "components" 和 "preprocess"',
        ),
    )
    required_fields = frozenset({"symbol", "trade_date"})

    def __init__(
        self,
        strategy_id: str,
        parameters: FactorCompositeParameters,
        components: tuple[FactorDefinition, ...],
    ) -> None:
        self.strategy_id = strategy_id
        self.config = parameters
        self._components = components

    @classmethod
    def from_parameters(
        cls, strategy_id: str, parameters: dict[str, Any]
    ) -> FactorCompositeStrategy:
        config = FactorCompositeParameters.from_json(str(parameters["factors_json"]))
        registry = default_registry()
        components = tuple(registry.get(item.name) for item in config.components)
        return cls(strategy_id, config, components)

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        fields = sorted({field for factor in self._components for field in factor.required_fields})
        lookback = max(factor.min_history for factor in self._components) + 1
        history = context.history(fields=fields, lookback=lookback)
        if history.empty:
            return []
        cutoff = pd.Timestamp(context.trade_date)

        frames: dict[str, pd.DataFrame] = {}
        weights: dict[str, float] = {}
        directions: dict[str, int] = {}
        for factor, component in zip(self._components, self.config.components, strict=True):
            try:
                values = factor.compute(history)
            except ValueError:
                continue  # 缺字段时跳过该因子而不是中断整个回测
            values["date"] = pd.to_datetime(values["date"]).dt.normalize()
            today = values[values["date"] == cutoff]
            if today.empty:
                continue
            frames[factor.name] = today
            weights[factor.name] = component.weight
            directions[factor.name] = factor.direction
        if not frames:
            return []

        composite = combine_factors(
            frames,
            weights,
            directions=directions,
            preprocess=self.config.preprocess,
        )
        signals: list[Signal] = []
        for row in composite.itertuples(index=False):
            signals.append(
                Signal(
                    strategy_id=self.strategy_id,
                    trade_date=context.trade_date,
                    symbol=str(row.symbol),
                    signal_type="FACTOR_COMPOSITE_SCORE",
                    score=float(row.value),
                    model_version="factor-composite-v1",
                )
            )
        return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))
