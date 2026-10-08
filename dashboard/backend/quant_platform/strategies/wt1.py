"""WT1 cross-sectional technical momentum strategy for A-shares."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, ClassVar, cast

import pandas as pd

from quant_platform.signals.models import Signal
from quant_platform.strategies.base import Strategy
from quant_platform.strategies.context import StrategyContext
from quant_platform.strategies.spec import ParameterKind, StrategyParameter

_MACD_FAST = 12
_MACD_SLOW = 26
_MACD_SIGNAL = 9
_LIQUIDITY_WINDOW = 20


@dataclass(frozen=True)
class WT1Parameters:
    """Configurable windows and entry requirements for WT1."""

    short_window: int = 20
    long_window: int = 60
    minimum_average_amount: float = 20_000_000.0
    ma_fast: int = 5
    ma_slow: int = 20
    kdj_period: int = 9
    minimum_score: float = 0.0


class WT1Strategy(Strategy):
    """Rank liquid positive-trend stocks using normalized technical factors."""

    plugin_name = "wt1"
    display_name = "WT1号"
    description = "动量、均线、MACD与KDJ横截面标准化综合策略；60日趋势过滤，次日开盘执行"
    parameters: ClassVar[tuple[StrategyParameter, ...]] = (
        StrategyParameter(
            "short_window",
            "短期动量周期",
            ParameterKind.INTEGER,
            20,
            "用于股票横截面动量排名的交易日数",
            minimum=5,
            maximum=120,
        ),
        StrategyParameter(
            "long_window",
            "长期趋势周期",
            ParameterKind.INTEGER,
            60,
            "只保留长期收益率为正的股票",
            minimum=20,
            maximum=250,
        ),
        StrategyParameter(
            "minimum_average_amount",
            "最低20日平均成交额",
            ParameterKind.NUMBER,
            20_000_000.0,
            "单位：元",
            minimum=0,
        ),
        StrategyParameter(
            "ma_fast",
            "快速均线周期",
            ParameterKind.INTEGER,
            5,
            minimum=2,
            maximum=60,
        ),
        StrategyParameter(
            "ma_slow",
            "慢速均线周期",
            ParameterKind.INTEGER,
            20,
            minimum=3,
            maximum=120,
        ),
        StrategyParameter(
            "kdj_period",
            "KDJ周期",
            ParameterKind.INTEGER,
            9,
            minimum=5,
            maximum=60,
        ),
        StrategyParameter(
            "minimum_score",
            "最低综合得分",
            ParameterKind.NUMBER,
            0.0,
            "标准化综合得分范围约为-1至1；低于该值时保留现金",
            minimum=-1.0,
            maximum=1.0,
        ),
    )
    required_fields = frozenset(
        {
            "symbol",
            "trade_date",
            "adjusted_close",
            "raw_close",
            "raw_high",
            "raw_low",
            "amount",
        }
    )

    def __init__(self, strategy_id: str, parameters: WT1Parameters) -> None:
        if not 0 < parameters.short_window < parameters.long_window:
            raise ValueError("WT1 windows must satisfy 0 < short_window < long_window")
        if not 0 < parameters.ma_fast < parameters.ma_slow:
            raise ValueError("WT1 moving averages must satisfy 0 < ma_fast < ma_slow")
        if parameters.kdj_period <= 0:
            raise ValueError("WT1 kdj_period must be positive")
        if parameters.minimum_average_amount < 0:
            raise ValueError("WT1 minimum_average_amount must not be negative")
        if not -1.0 <= parameters.minimum_score <= 1.0:
            raise ValueError("WT1 minimum_score must be between -1 and 1")
        self.strategy_id = strategy_id
        self.config = parameters

    @classmethod
    def from_parameters(cls, strategy_id: str, parameters: dict[str, Any]) -> WT1Strategy:
        """Build WT1 from catalog-validated values."""

        return cls(
            strategy_id,
            WT1Parameters(
                short_window=int(parameters["short_window"]),
                long_window=int(parameters["long_window"]),
                minimum_average_amount=float(parameters["minimum_average_amount"]),
                ma_fast=int(parameters["ma_fast"]),
                ma_slow=int(parameters["ma_slow"]),
                kdj_period=int(parameters["kdj_period"]),
                minimum_score=float(parameters["minimum_score"]),
            ),
        )

    def generate_signals(self, context: StrategyContext) -> list[Signal]:
        """Calculate point-in-time WT1 scores for the supplied universe."""

        context.require_fields(self.required_fields)
        lookback = max(
            self.config.long_window + 1,
            self.config.short_window + 1,
            self.config.ma_slow,
            self.config.kdj_period,
            _MACD_SLOW + _MACD_SIGNAL - 1,
            _LIQUIDITY_WINDOW,
        )
        history = context.history(
            fields=[
                "adjusted_close",
                "raw_close",
                "raw_high",
                "raw_low",
                "amount",
            ],
            lookback=lookback,
        )
        cutoff = pd.Timestamp(context.trade_date)
        candidates: list[dict[str, str | float]] = []

        for symbol, original in history.groupby("symbol", observed=True):
            group = original.sort_values("trade_date").copy()
            if group.empty or pd.Timestamp(group.iloc[-1]["trade_date"]) != cutoff:
                continue
            if len(group) < lookback:
                continue

            numeric_columns = [
                "adjusted_close",
                "raw_close",
                "raw_high",
                "raw_low",
                "amount",
            ]
            group[numeric_columns] = group[numeric_columns].apply(
                pd.to_numeric, errors="coerce"
            )
            close = group["adjusted_close"]
            current = float(close.iloc[-1])
            short_base = float(close.iloc[-self.config.short_window - 1])
            long_base = float(close.iloc[-self.config.long_window - 1])
            if not _all_positive_finite(current, short_base, long_base):
                continue

            long_momentum = current / long_base - 1.0
            if long_momentum <= 0:
                continue

            recent_amount = group["amount"].tail(_LIQUIDITY_WINDOW)
            if recent_amount.notna().sum() < _LIQUIDITY_WINDOW:
                continue
            average_amount = float(recent_amount.mean())
            if not isfinite(average_amount) or average_amount < self.config.minimum_average_amount:
                continue

            factor_values = {
                "momentum": current / short_base - 1.0,
                "ma": _ma_spread(close, self.config.ma_fast, self.config.ma_slow),
                "macd": _normalized_macd_histogram(close),
                "kdj": _kdj_momentum(
                    group["raw_high"],
                    group["raw_low"],
                    group["raw_close"],
                    self.config.kdj_period,
                ),
            }
            if not all(isfinite(value) for value in factor_values.values()):
                continue
            candidates.append({"symbol": str(symbol), **factor_values})

        if not candidates:
            return []

        scored = pd.DataFrame(candidates)
        weights = {"momentum": 0.45, "ma": 0.20, "macd": 0.20, "kdj": 0.15}
        scored["score"] = 0.0
        for factor, weight in weights.items():
            scored["score"] += _centered_rank(scored[factor]) * weight

        signals = [
            Signal(
                strategy_id=self.strategy_id,
                trade_date=context.trade_date,
                symbol=str(row.symbol),
                signal_type="WT1_COMPOSITE_SCORE",
                score=float(cast(Any, row.score)),
                model_version="WT1-v1",
            )
            for row in scored.itertuples(index=False)
            if float(cast(Any, row.score)) >= self.config.minimum_score
        ]
        return sorted(signals, key=lambda signal: (-signal.score, signal.symbol))


def _all_positive_finite(*values: float) -> bool:
    return all(isfinite(value) and value > 0 for value in values)


def _ma_spread(close: pd.Series, fast: int, slow: int) -> float:
    fast_average = float(close.tail(fast).mean())
    slow_average = float(close.tail(slow).mean())
    if not _all_positive_finite(fast_average, slow_average):
        return float("nan")
    return fast_average / slow_average - 1.0


def _normalized_macd_histogram(close: pd.Series) -> float:
    if close.notna().sum() < _MACD_SLOW + _MACD_SIGNAL - 1:
        return float("nan")
    fast = close.ewm(span=_MACD_FAST, adjust=False, min_periods=_MACD_FAST).mean()
    slow = close.ewm(span=_MACD_SLOW, adjust=False, min_periods=_MACD_SLOW).mean()
    macd = fast - slow
    signal = macd.ewm(span=_MACD_SIGNAL, adjust=False, min_periods=_MACD_SIGNAL).mean()
    latest_close = float(close.iloc[-1])
    histogram = float((macd - signal).iloc[-1])
    if not _all_positive_finite(latest_close) or not isfinite(histogram):
        return float("nan")
    return histogram / latest_close


def _kdj_momentum(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> float:
    lowest = low.rolling(period, min_periods=period).min()
    highest = high.rolling(period, min_periods=period).max()
    price_range = highest - lowest
    rsv = ((close - lowest) / price_range.where(price_range > 0) * 100.0).clip(0.0, 100.0)
    k = rsv.ewm(alpha=1.0 / 3.0, adjust=False, min_periods=period).mean()
    d = k.ewm(alpha=1.0 / 3.0, adjust=False, min_periods=period).mean()
    value = float((k - d).iloc[-1]) / 100.0
    return value if isfinite(value) else float("nan")


def _centered_rank(values: pd.Series) -> pd.Series:
    """Map cross-sectional ranks to [-1, 1], with one observation mapped to zero."""

    if len(values) == 1:
        return pd.Series(0.0, index=values.index, dtype=float)
    ranks = values.rank(method="average", ascending=True)
    return (ranks - 1.0) / (len(values) - 1.0) * 2.0 - 1.0

