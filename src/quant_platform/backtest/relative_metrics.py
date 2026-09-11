"""Aligned benchmark-relative statistics; undefined estimates stay missing."""

import numpy as np
import pandas as pd


def relative_metrics(nav: pd.DataFrame, periods: int = 252, risk_free_rate: float = 0.0) -> dict:
    if "benchmark_equity" not in nav:
        return {}
    prices = nav.sort_values("trade_date")[["equity", "benchmark_equity"]].apply(
        pd.to_numeric, errors="coerce"
    )
    returns = prices.pct_change(fill_method=None).replace([np.inf, -np.inf], np.nan).dropna()
    result = {
        "tracking_error": None,
        "information_ratio": None,
        "regression_alpha": None,
        "beta": None,
        "relative_observations": len(returns),
    }
    if len(returns) < 3:
        return result
    active = returns.equity - returns.benchmark_equity
    deviation = float(active.std(ddof=1))
    result["tracking_error"] = deviation * np.sqrt(periods)
    if deviation > 1e-12:
        result["information_ratio"] = float(active.mean() / deviation * np.sqrt(periods))
    rf = (1 + risk_free_rate) ** (1 / periods) - 1
    x, y = returns.benchmark_equity - rf, returns.equity - rf
    if x.var(ddof=1) > 1e-16:
        beta = float(x.cov(y) / x.var(ddof=1))
        result["beta"] = beta
        result["regression_alpha"] = float((y.mean() - beta * x.mean()) * periods)
    return result
