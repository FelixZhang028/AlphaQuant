"""Backtest performance metrics."""

from __future__ import annotations

import math

import pandas as pd


def calculate_metrics(nav: pd.DataFrame) -> dict[str, float]:
    """Calculate basic daily-frequency performance statistics."""

    if nav.empty:
        return {}
    equity = pd.to_numeric(nav["equity"], errors="coerce").dropna()
    if equity.empty:
        return {}
    returns = equity.pct_change().dropna()
    cumulative_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    periods = max(len(equity) - 1, 1)
    annual_return = float((equity.iloc[-1] / equity.iloc[0]) ** (252 / periods) - 1.0)
    annual_volatility = (
        float(returns.std(ddof=1) * math.sqrt(252)) if len(returns) > 1 else 0.0
    )
    sharpe = annual_return / annual_volatility if annual_volatility > 0 else 0.0
    running_peak = equity.cummax()
    max_drawdown = float((equity / running_peak - 1.0).min())
    return {
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
    }
