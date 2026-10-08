"""SCH1 offense-defense rotation strategy for A-shares."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Any, ClassVar, cast

import pandas as pd

from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyParameter

_TRADING_DAYS = 244
_SUSPENSION_FILL_LIMIT = 60


@dataclass(frozen=True)
class SCH1Parameters:
    """Configurable factor windows and rotation rules for SCH1."""

    momentum_lookback: int = 252
    momentum_skip: int = 21
    volatility_window: int = 125
    trend_ma: int = 250
    stock_ma: int = 200
    minimum_listed_days: int = 150
    hysteresis: float = 0.01
    brake_drawdown: float = 0.15
    offense_top_n: int = 15
    defense_top_n: int = 10


class SCH1Strategy(Strategy):
    """Rotate between risk-adjusted momentum and low-volatility stocks."""

    plugin_name = "sch1"
    display_name = "SCH1号"
    description = (
        "月频攻守轮动：趋势向上时持有12-1月风险调整动量股，"
        "趋势转弱或组合回撤超过阈值时持有低波动股；请使用月度调仓"
    )
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "momentum_lookback",
            "动量回看周期",
            ParameterKind.INTEGER,
            252,
            "长期动量起点，单位为交易日",
            minimum=120,
            maximum=500,
        ),
        StrategyParameter(
            "momentum_skip",
            "跳过最近周期",
            ParameterKind.INTEGER,
            21,
            "计算动量时跳过最近交易日，规避短期反转",
            minimum=5,
            maximum=60,
        ),
        StrategyParameter(
            "volatility_window",
            "波动率周期",
            ParameterKind.INTEGER,
            125,
            "风险调整动量及防御选股使用的交易日数",
            minimum=60,
            maximum=250,
        ),
        StrategyParameter(
            "trend_ma",
            "市场趋势均线",
            ParameterKind.INTEGER,
            250,
            minimum=120,
            maximum=500,
        ),
        StrategyParameter(
            "stock_ma",
            "个股趋势均线",
            ParameterKind.INTEGER,
            200,
            minimum=60,
            maximum=500,
        ),
        StrategyParameter(
            "minimum_listed_days",
            "最少上市交易日",
            ParameterKind.INTEGER,
            150,
            minimum=60,
            maximum=500,
        ),
        StrategyParameter(
            "hysteresis",
            "趋势滞回带",
            ParameterKind.NUMBER,
            0.01,
            "1%表示指数高于均线1%才进攻、低于均线1%才防御",
            minimum=0.0,
            maximum=0.10,
        ),
        StrategyParameter(
            "brake_drawdown",
            "净值刹车回撤",
            ParameterKind.NUMBER,
            0.15,
            "组合从历史峰值回撤达到该比例时强制进入防御模式",
            minimum=0.01,
            maximum=0.50,
        ),
        StrategyParameter(
            "offense_top_n",
            "进攻持股数",
            ParameterKind.INTEGER,
            15,
            minimum=1,
            maximum=50,
        ),
        StrategyParameter(
            "defense_top_n",
            "防御持股数",
            ParameterKind.INTEGER,
            10,
            minimum=1,
            maximum=50,
        ),
    )
    required_fields = frozenset({"symbol", "trade_date", "adjusted_close"})

    def __init__(self, strategy_id: str, parameters: SCH1Parameters) -> None:
        if not 0 < parameters.momentum_skip < parameters.momentum_lookback:
            raise ValueError("SCH1 momentum windows must satisfy 0 < skip < lookback")
        if parameters.volatility_window <= 1:
            raise ValueError("SCH1 volatility_window must be greater than one")
        if parameters.trend_ma <= 1 or parameters.stock_ma <= 1:
            raise ValueError("SCH1 moving-average windows must be greater than one")
        if parameters.minimum_listed_days <= 0:
            raise ValueError("SCH1 minimum_listed_days must be positive")
        if not 0.0 <= parameters.hysteresis < 1.0:
            raise ValueError("SCH1 hysteresis must be between zero and one")
        if not 0.0 < parameters.brake_drawdown < 1.0:
            raise ValueError("SCH1 brake_drawdown must be between zero and one")
        if parameters.offense_top_n <= 0 or parameters.defense_top_n <= 0:
            raise ValueError("SCH1 target counts must be positive")
        self.strategy_id = strategy_id
        self.config = parameters

    @classmethod
    def from_parameters(cls, strategy_id: str, parameters: dict[str, Any]) -> SCH1Strategy:
        """Build SCH1 from catalog-validated parameters."""

        return cls(
            strategy_id,
            SCH1Parameters(
                momentum_lookback=int(parameters["momentum_lookback"]),
                momentum_skip=int(parameters["momentum_skip"]),
                volatility_window=int(parameters["volatility_window"]),
                trend_ma=int(parameters["trend_ma"]),
                stock_ma=int(parameters["stock_ma"]),
                minimum_listed_days=int(parameters["minimum_listed_days"]),
                hysteresis=float(parameters["hysteresis"]),
                brake_drawdown=float(parameters["brake_drawdown"]),
                offense_top_n=int(parameters["offense_top_n"]),
                defense_top_n=int(parameters["defense_top_n"]),
            ),
        )

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """Generate one explicit-weight offense or defense target portfolio."""

        context.require_fields(self.required_fields)
        history = context.history(fields=["adjusted_close"])
        close = (
            history.pivot_table(
                index="trade_date",
                columns="symbol",
                values="adjusted_close",
                aggfunc="last",
            )
            .sort_index()
            .apply(pd.to_numeric, errors="coerce")
        )
        cutoff = pd.Timestamp(context.trade_date)
        if cutoff not in close.index:
            return []

        required_history = max(
            self.config.momentum_lookback,
            self.config.volatility_window,
            self.config.trend_ma,
            self.config.stock_ma,
            self.config.minimum_listed_days,
        )
        position = cast(int, close.index.get_loc(cutoff))
        if position < required_history:
            return []

        filled_close = close.ffill(limit=_SUSPENSION_FILL_LIMIT)
        returns = filled_close.pct_change(fill_method=None)
        risk_on = _risk_on_state(returns, cutoff, self.config)
        braked = context.portfolio_drawdown <= -self.config.brake_drawdown
        mode = "offense" if risk_on and not braked else "defense"

        mask, momentum, volatility = _eligible_factors(
            close,
            returns,
            cutoff,
            self.config,
        )
        if mode == "offense":
            moving_average = close.rolling(
                self.config.stock_ma,
                min_periods=self.config.stock_ma,
            ).mean().loc[cutoff]
            above_average = close.loc[cutoff] > moving_average
            score = (momentum / volatility).where(
                mask & above_average.fillna(False) & momentum.gt(0.0)
            )
            selected = score.dropna().sort_values(ascending=False).head(
                self.config.offense_top_n
            )
            if selected.empty:
                mode = "defense"

        if mode == "defense":
            score = (-volatility).where(mask)
            selected = score.dropna().sort_values(ascending=False).head(
                self.config.defense_top_n
            )

        if selected.empty:
            return []
        target_weight = 1.0 / len(selected)
        signal_type = "SCH1_OFFENSE" if mode == "offense" else "SCH1_DEFENSE"
        signals = [
            Signal(
                strategy_id=self.strategy_id,
                trade_date=context.trade_date,
                symbol=str(symbol),
                signal_type=signal_type,
                score=float(value),
                target_weight=target_weight,
                model_version="SCH1-v1",
            )
            for symbol, value in selected.items()
            if isfinite(float(value))
        ]
        return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))


def _risk_on_state(
    returns: pd.DataFrame,
    cutoff: pd.Timestamp,
    config: SCH1Parameters,
) -> bool:
    market_level = (1.0 + returns.mean(axis=1).fillna(0.0)).cumprod()
    trend_average = market_level.rolling(
        config.trend_ma,
        min_periods=config.trend_ma,
    ).mean()
    ratio = market_level / trend_average
    ratio_dates = pd.DatetimeIndex(ratio.index)
    month_end_ratio = ratio.groupby([ratio_dates.year, ratio_dates.month]).tail(1)
    risk_on = False
    for value in month_end_ratio.loc[:cutoff].dropna():
        number = float(value)
        if risk_on and number < 1.0 - config.hysteresis:
            risk_on = False
        elif not risk_on and number > 1.0 + config.hysteresis:
            risk_on = True
    return risk_on


def _eligible_factors(
    close: pd.DataFrame,
    returns: pd.DataFrame,
    cutoff: pd.Timestamp,
    config: SCH1Parameters,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    position = cast(int, close.index.get_loc(cutoff))
    current = close.iloc[position]
    momentum_end = close.iloc[position - config.momentum_skip]
    momentum_start = close.iloc[position - config.momentum_lookback]
    momentum = momentum_end / momentum_start - 1.0
    volatility = (
        returns.iloc[position - config.volatility_window + 1 : position + 1].std()
        * sqrt(_TRADING_DAYS)
    )
    listed_days = close.iloc[: position + 1].notna().sum()
    mask = (
        listed_days.ge(config.minimum_listed_days)
        & current.notna()
        & momentum_end.notna()
        & momentum_start.notna()
        & volatility.gt(0.0)
        & volatility.map(lambda value: isfinite(float(value)) if pd.notna(value) else False)
    )
    return mask, momentum, volatility
