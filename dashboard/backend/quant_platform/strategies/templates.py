"""Beginner-friendly P0 strategy templates and three risk-style presets."""

from __future__ import annotations

from dataclasses import dataclass

from quant_platform.strategies.rule_schema import (
    IndicatorSpec,
    RankingSpec,
    RuleSpec,
    RuleStrategyDefinition,
)

STYLE_LABELS = {
    "conservative": "保守",
    "balanced": "均衡",
    "aggressive": "激进",
}


@dataclass(frozen=True)
class StrategyPreset:
    definition: RuleStrategyDefinition
    top_n: int
    rebalance: str


@dataclass(frozen=True)
class BeginnerTemplate:
    template_id: str
    name: str
    summary: str
    suitable_market: str
    main_risk: str
    presets: dict[str, StrategyPreset]


def beginner_templates() -> tuple[BeginnerTemplate, ...]:
    """Return a stable catalog of six executable zero-code templates."""

    return (
        _momentum_template(),
        _trend_template(),
        _low_volatility_template(),
        _breakout_template(),
        _mean_reversion_template(),
        _multi_trend_template(),
    )


def get_beginner_template(template_id: str) -> BeginnerTemplate:
    for template in beginner_templates():
        if template.template_id == template_id:
            return template
    raise ValueError(f"未知策略模板：{template_id}")


def _indicator(name: str, window: int | None = None) -> IndicatorSpec:
    return IndicatorSpec(name, window)


def _constant(left: IndicatorSpec, operator: str, value: float) -> RuleSpec:
    return RuleSpec(left=left, operator=operator, value=value)


def _compare(left: IndicatorSpec, operator: str, right: IndicatorSpec) -> RuleSpec:
    return RuleSpec(left=left, operator=operator, right=right)


def _definition(
    template_id: str,
    style: str,
    name: str,
    description: str,
    rules: tuple[RuleSpec, ...],
    ranking: IndicatorSpec,
    direction: str = "descending",
) -> RuleStrategyDefinition:
    result = RuleStrategyDefinition(
        strategy_id=f"{template_id}_{style}",
        name=f"{name}·{STYLE_LABELS[style]}",
        description=description,
        entry_logic="all",
        entry_rules=rules,
        ranking=RankingSpec(ranking, direction),
    )
    result.validate()
    return result


def _momentum_template() -> BeginnerTemplate:
    presets: dict[str, StrategyPreset] = {}
    settings = {
        "conservative": (60, 120, 8, "monthly"),
        "balanced": (20, 60, 5, "weekly"),
        "aggressive": (10, 20, 3, "weekly"),
    }
    for style, (short, long, top_n, rebalance) in settings.items():
        definition = _definition(
            "momentum",
            style,
            "动量选股",
            "选择中长期趋势向上且流动性充足的强势股票。",
            (
                _constant(_indicator("return", long), "greater_than", 0.0),
                _constant(_indicator("average_amount", 20), "greater_than", 20_000_000),
            ),
            _indicator("return", short),
        )
        presets[style] = StrategyPreset(definition, top_n, rebalance)
    return BeginnerTemplate(
        "momentum",
        "动量选股",
        "买入近期表现较强、长期趋势仍向上的股票。",
        "趋势明确、强者恒强的市场",
        "震荡行情中可能频繁追高回撤",
        presets,
    )


def _trend_template() -> BeginnerTemplate:
    presets: dict[str, StrategyPreset] = {}
    settings = {
        "conservative": (120, 60, 10, "monthly"),
        "balanced": (60, 20, 6, "weekly"),
        "aggressive": (20, 10, 4, "weekly"),
    }
    for style, (ma, momentum, top_n, rebalance) in settings.items():
        definition = _definition(
            "ma_trend",
            style,
            "均线趋势",
            "价格位于趋势均线上方时参与，并优先选择近期较强股票。",
            (
                _compare(
                    _indicator("close"),
                    "greater_than",
                    _indicator("moving_average", ma),
                ),
                _constant(_indicator("average_amount", 20), "greater_than", 20_000_000),
            ),
            _indicator("return", momentum),
        )
        presets[style] = StrategyPreset(definition, top_n, rebalance)
    return BeginnerTemplate(
        "ma_trend",
        "均线趋势",
        "股价站上均线后参与趋势。",
        "持续上涨或缓慢上行市场",
        "横盘时可能产生反复买卖",
        presets,
    )


def _low_volatility_template() -> BeginnerTemplate:
    presets: dict[str, StrategyPreset] = {}
    settings = {
        "conservative": (60, 120, 10, "monthly"),
        "balanced": (40, 60, 8, "monthly"),
        "aggressive": (20, 20, 5, "weekly"),
    }
    for style, (volatility, trend, top_n, rebalance) in settings.items():
        definition = _definition(
            "low_volatility",
            style,
            "低波动",
            "在趋势非负的股票中优先选择历史波动较小的股票。",
            (
                _constant(_indicator("return", trend), "greater_or_equal", 0.0),
                _constant(_indicator("average_amount", 20), "greater_than", 20_000_000),
            ),
            _indicator("volatility", volatility),
            "ascending",
        )
        presets[style] = StrategyPreset(definition, top_n, rebalance)
    return BeginnerTemplate(
        "low_volatility",
        "低波动",
        "优先持有价格波动较小的股票。",
        "震荡或风险偏好下降的市场",
        "强牛市中可能明显落后于高弹性股票",
        presets,
    )


def _breakout_template() -> BeginnerTemplate:
    presets: dict[str, StrategyPreset] = {}
    settings = {
        "conservative": (120, 60, 8, "monthly"),
        "balanced": (60, 20, 5, "weekly"),
        "aggressive": (20, 10, 3, "weekly"),
    }
    for style, (high_window, rank_window, top_n, rebalance) in settings.items():
        definition = _definition(
            "breakout",
            style,
            "突破新高",
            "收盘价突破前期高点后参与，并优先选择突破较强的股票。",
            (
                _compare(
                    _indicator("close"),
                    "greater_than",
                    _indicator("previous_high", high_window),
                ),
                _constant(_indicator("average_amount", 20), "greater_than", 20_000_000),
            ),
            _indicator("return", rank_window),
        )
        presets[style] = StrategyPreset(definition, top_n, rebalance)
    return BeginnerTemplate(
        "breakout",
        "突破新高",
        "突破一段时间最高收盘价后买入。",
        "趋势启动和放量突破行情",
        "假突破可能造成快速亏损",
        presets,
    )


def _mean_reversion_template() -> BeginnerTemplate:
    presets: dict[str, StrategyPreset] = {}
    settings = {
        "conservative": (10, -0.06, 120, 10, "monthly"),
        "balanced": (5, -0.03, 60, 6, "weekly"),
        "aggressive": (3, -0.015, 20, 4, "weekly"),
    }
    for style, (window, threshold, ma, top_n, rebalance) in settings.items():
        definition = _definition(
            "mean_reversion",
            style,
            "均值回归",
            "在中期趋势未破坏时，选择短期跌幅较大的股票等待反弹。",
            (
                _constant(_indicator("return", window), "less_than", threshold),
                _compare(
                    _indicator("close"),
                    "greater_than",
                    _indicator("moving_average", ma),
                ),
                _constant(_indicator("average_amount", 20), "greater_than", 20_000_000),
            ),
            _indicator("return", window),
            "ascending",
        )
        presets[style] = StrategyPreset(definition, top_n, rebalance)
    return BeginnerTemplate(
        "mean_reversion",
        "均值回归",
        "选择趋势未坏但短期下跌过多的股票。",
        "区间震荡、短期超跌后修复的市场",
        "单边下跌时可能不断接住下跌股票",
        presets,
    )


def _multi_trend_template() -> BeginnerTemplate:
    presets: dict[str, StrategyPreset] = {}
    settings = {
        "conservative": (60, 180, 120, 10, "monthly"),
        "balanced": (20, 60, 60, 6, "weekly"),
        "aggressive": (10, 30, 20, 4, "weekly"),
    }
    for style, (fast, slow, rank_window, top_n, rebalance) in settings.items():
        definition = _definition(
            "multi_trend",
            style,
            "多周期趋势",
            "短期均线高于长期均线且价格保持在长期均线上方。",
            (
                _compare(
                    _indicator("moving_average", fast),
                    "greater_than",
                    _indicator("moving_average", slow),
                ),
                _compare(
                    _indicator("close"),
                    "greater_than",
                    _indicator("moving_average", slow),
                ),
                _constant(_indicator("average_amount", 20), "greater_than", 20_000_000),
            ),
            _indicator("return", rank_window),
        )
        presets[style] = StrategyPreset(definition, top_n, rebalance)
    return BeginnerTemplate(
        "multi_trend",
        "多周期趋势",
        "短期和长期趋势同时向上时参与。",
        "中期趋势比较稳定的市场",
        "确认较慢，可能错过行情早期",
        presets,
    )
