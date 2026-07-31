"""Return and risk metrics for daily-frequency backtests."""

from __future__ import annotations

import math
from typing import Any, cast

import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def calculate_metrics(
    nav: pd.DataFrame,
    *,
    initial_cash: float | None = None,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    """Calculate robust absolute-return and drawdown statistics."""

    prepared = _prepare_nav(nav)
    if prepared.empty:
        return {}
    equity = prepared["equity"]
    starting_equity = float(initial_cash) if initial_cash else float(equity.iloc[0])
    if starting_equity <= 0:
        raise ValueError("initial equity must be positive")

    returns = cast(pd.Series, equity.pct_change().dropna())
    periods = max(len(equity) - 1, 1)
    cumulative_return = float(equity.iloc[-1] / starting_equity - 1.0)
    total_ratio = float(equity.iloc[-1] / starting_equity)
    annual_return = (
        float(total_ratio ** (TRADING_DAYS_PER_YEAR / periods) - 1.0) if total_ratio > 0 else -1.0
    )
    annual_volatility = _annualized_std(returns)

    daily_risk_free = (1.0 + risk_free_rate) ** (1.0 / TRADING_DAYS_PER_YEAR) - 1.0
    excess_returns = cast(pd.Series, returns - daily_risk_free)
    sharpe = _annualized_ratio(excess_returns, annual_volatility)
    downside = excess_returns[excess_returns < 0]
    downside_volatility = (
        float(math.sqrt(float((downside**2).mean())) * math.sqrt(TRADING_DAYS_PER_YEAR))
        if not downside.empty
        else 0.0
    )
    sortino = _annualized_ratio(excess_returns, downside_volatility)

    drawdown = calculate_drawdown_series(prepared)
    drawdown_metrics = _drawdown_metrics(prepared, drawdown)
    max_drawdown = float(drawdown_metrics["max_drawdown"])
    calmar = annual_return / abs(max_drawdown) if max_drawdown < -1e-12 else None

    monthly = calculate_monthly_returns(prepared)
    return {
        "cumulative_return": cumulative_return,
        "annual_return": annual_return,
        "annual_volatility": annual_volatility,
        "downside_volatility": downside_volatility,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "risk_free_rate": risk_free_rate,
        "best_day_return": float(returns.max()) if not returns.empty else 0.0,
        "worst_day_return": float(returns.min()) if not returns.empty else 0.0,
        "positive_day_ratio": (float((returns > 0).mean()) if not returns.empty else 0.0),
        "positive_month_ratio": (
            float((monthly["return"] > 0).mean()) if not monthly.empty else 0.0
        ),
        "return_observations": len(returns),
        **drawdown_metrics,
    }


def calculate_drawdown_series(nav: pd.DataFrame) -> pd.DataFrame:
    """Return the point-in-time drawdown curve for charting."""

    prepared = _prepare_nav(nav)
    if prepared.empty:
        return pd.DataFrame(columns=["trade_date", "drawdown"])
    equity = prepared["equity"]
    running_peak = equity.cummax()
    return pd.DataFrame(
        {
            "trade_date": prepared["trade_date"],
            "drawdown": equity.div(running_peak).sub(1.0),
        }
    )


def calculate_monthly_returns(nav: pd.DataFrame) -> pd.DataFrame:
    """Compound daily returns into calendar-month returns."""

    prepared = _prepare_nav(nav)
    if prepared.empty:
        return pd.DataFrame(columns=["month", "year", "month_number", "return"])
    working = prepared[["trade_date", "equity"]].copy()
    equity = working["equity"]
    working["daily_return"] = equity.pct_change().fillna(0.0)
    working["period"] = working["trade_date"].dt.to_period("M")
    monthly = (
        working.groupby("period", observed=True)["daily_return"]
        .apply(_compound_returns)
        .rename("return")
        .reset_index()
    )
    monthly["month"] = monthly["period"].astype(str)
    monthly["year"] = monthly["period"].dt.year
    monthly["month_number"] = monthly["period"].dt.month
    return monthly[["month", "year", "month_number", "return"]]


def _compound_returns(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0)
    product = float(cast(Any, numeric.add(1.0).prod()))
    return product - 1.0


def _prepare_nav(nav: pd.DataFrame) -> pd.DataFrame:
    required = {"trade_date", "equity"}
    if nav.empty or not required.issubset(nav.columns):
        return pd.DataFrame(columns=["trade_date", "equity"])
    prepared = nav[["trade_date", "equity"]].copy()
    prepared["trade_date"] = pd.to_datetime(prepared["trade_date"], errors="coerce")
    prepared["equity"] = pd.to_numeric(prepared["equity"], errors="coerce")
    return (
        prepared.dropna()
        .sort_values("trade_date")
        .drop_duplicates("trade_date", keep="last")
        .reset_index(drop=True)
    )


def _annualized_std(returns: pd.Series) -> float:
    if len(returns) <= 1:
        return 0.0
    return float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))


def _annualized_ratio(returns: pd.Series, annualized_risk: float) -> float | None:
    if returns.empty or annualized_risk <= 0:
        return None
    annualized_excess = float(returns.mean() * TRADING_DAYS_PER_YEAR)
    return annualized_excess / annualized_risk


def _drawdown_metrics(nav: pd.DataFrame, drawdown: pd.DataFrame) -> dict[str, Any]:
    values = drawdown["drawdown"]
    trough_index = int(values.idxmin())
    prior_equity = nav.loc[:trough_index, "equity"]
    peak_index = int(prior_equity.idxmax())
    peak_equity = float(cast(Any, nav.loc[peak_index, "equity"]))
    after_trough = nav.loc[trough_index + 1 :]
    recovered = after_trough[after_trough["equity"].ge(peak_equity)]
    recovery_index = int(recovered.index[0]) if not recovered.empty else None
    duration_end = recovery_index if recovery_index is not None else len(nav) - 1
    peak_date = pd.Timestamp(cast(Any, nav.loc[peak_index, "trade_date"]))
    trough_date = pd.Timestamp(cast(Any, nav.loc[trough_index, "trade_date"]))
    recovery_date = (
        pd.Timestamp(cast(Any, nav.loc[recovery_index, "trade_date"]))
        if recovery_index is not None
        else None
    )
    return {
        "max_drawdown": float(cast(Any, values.iloc[trough_index])),
        "max_drawdown_start_date": peak_date.date().isoformat(),
        "max_drawdown_trough_date": trough_date.date().isoformat(),
        "max_drawdown_recovery_date": (
            recovery_date.date().isoformat() if recovery_date is not None else None
        ),
        "max_drawdown_duration_trading_days": max(duration_end - peak_index, 0),
    }
