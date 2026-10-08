"""Long-only allocation from trailing returns, plus explicit turnover budgets."""

from dataclasses import replace

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from quant_platform.factors.base import pivot_field
from quant_platform.portfolio.equal_weight import EqualWeightPortfolio
from quant_platform.portfolio.models import TargetPosition


class RiskWeightedPortfolio(EqualWeightPortfolio):
    def __init__(self, top_n: int, method: str, lookback: int = 60) -> None:
        super().__init__(top_n)
        if method not in {"inverse_volatility", "risk_parity", "mean_variance"}:
            raise ValueError("未知组合权重方法")
        self.method = method
        self.lookback = lookback

    def construct_with_history(self, signals, history):
        targets = super().construct(signals)
        if not targets or any(signal.target_weight is not None for signal in signals):
            return targets
        names = [target.symbol for target in targets]
        cutoff = min(target.signal_date for target in targets)
        history = history[pd.to_datetime(history.trade_date) <= pd.Timestamp(cutoff)]
        close = pivot_field(history, "adjusted_close").reindex(columns=names)
        returns = close.tail(self.lookback + 1).pct_change(fill_method=None).dropna()
        if len(returns) < 20:
            raise ValueError("风险组合需要至少20个完整收益观测，请增加预热或补齐行情")
        covariance = returns.cov().to_numpy() + np.eye(len(names)) * 1e-8
        vol = np.sqrt(np.diag(covariance))
        initial = 1 / vol
        initial /= initial.sum()
        if self.method == "inverse_volatility":
            weights = initial
        else:

            def objective(w):
                variance = w @ covariance @ w
                if self.method == "risk_parity":
                    contribution = w * (covariance @ w) / variance
                    return float(np.sum((contribution - 1 / len(w)) ** 2))
                # Fixed risk aversion and shrunk expected returns; not auto-tuned.
                return float(5 * variance - w @ (returns.mean().to_numpy() * 0.5))

            solution = minimize(
                objective,
                initial,
                method="SLSQP",
                bounds=[(0, 1)] * len(names),
                constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                options={"ftol": 1e-12, "maxiter": 1000},
            )
            if not solution.success:
                raise ValueError(f"组合优化失败：{solution.message}")
            weights = np.maximum(solution.x, 0)
            weights /= weights.sum()
        return [
            replace(target, target_weight=float(w))
            for target, w in zip(targets, weights, strict=True)
            if w > 1e-12
        ]


def constrain_turnover(
    targets: list[TargetPosition],
    current: dict[str, float],
    budget: float,
    *,
    reference: TargetPosition | None = None,
) -> list[TargetPosition]:
    """Limit sum(abs(delta stock weights)); a full cash-to-stock buy is 1.0."""
    desired = {target.symbol: target.target_weight for target in targets}
    names = sorted(set(current) | set(desired))
    turnover = sum(abs(desired.get(n, 0) - current.get(n, 0)) for n in names)
    if turnover <= budget:
        return targets
    scale = budget / turnover
    reference = targets[0] if targets else reference
    if reference is None:
        raise ValueError("限制清仓换手需要策略和信号日期")
    return [
        replace(reference, symbol=name, target_weight=weight)
        for name in names
        if (weight := current.get(name, 0) + scale * (desired.get(name, 0) - current.get(name, 0)))
        > 1e-12
    ]
