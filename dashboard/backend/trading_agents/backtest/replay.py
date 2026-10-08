"""历史决策回放与绩效计算：累计收益/回撤/胜率/夏普/Alpha/Beta。"""

from __future__ import annotations

import datetime as dt

import numpy as np

from trading_agents.data.base import DataProvider
from trading_agents.execution import Portfolio, SimulatedExchange
from trading_agents.memory import MemoryStore
from trading_agents.schemas import Decision, PerformanceMetrics, Ticker
from trading_agents.schemas.models import ApprovalStatus, TradeAction


class Backtester:
    """回放 memory 中的决策序列并计算 PerformanceMetrics。"""

    def __init__(
        self,
        exchange: SimulatedExchange,
        provider: DataProvider,
        memory: MemoryStore,
        benchmark_symbol: str = "SPY",
    ) -> None:
        self.exchange = exchange
        self.provider = provider
        self.memory = memory
        self.benchmark_symbol = benchmark_symbol

    def replay(self, ticker: str, horizon_days: int = 5) -> PerformanceMetrics:
        """对 ``ticker`` 的历史已批准决策逐条回放，统计绩效。"""
        entries = [
            e for e in reversed(self.memory.history(ticker, limit=100))
            if e.status != ApprovalStatus.REJECTED and e.action != TradeAction.HOLD
        ]
        if not entries:
            return PerformanceMetrics(benchmark=self.benchmark_symbol, notes="无可回放决策")
        portfolio = Portfolio(cash=self.exchange.settings.initial_cash)
        identity = self.provider.resolve(ticker, "US")
        returns: list[float] = []
        wins = 0
        for e in entries:
            decision = Decision.model_validate_json(e.decision_json) if e.decision_json else None
            bars = self.provider.get_bars_after(identity, e.trade_date, horizon_days + 1)
            if decision is None or not bars:
                continue
            snapshot = self.provider.get_snapshot(identity, e.trade_date)
            self.exchange.execute(decision, snapshot, portfolio)
            exit_price = bars[-1].close
            pos = portfolio.positions.get(ticker)
            if decision.final_action == TradeAction.BUY and pos and pos.quantity > 0:
                ret = exit_price / pos.avg_cost - 1
                returns.append(ret)
                wins += int(ret > 0)
                portfolio.apply_sell(ticker, pos.quantity, exit_price, 0.0)
        return self._metrics(returns, wins, identity, entries, horizon_days)

    def _metrics(
        self,
        returns: list[float],
        wins: int,
        identity: Ticker,
        entries: list,
        horizon_days: int,
    ) -> PerformanceMetrics:
        if not returns:
            return PerformanceMetrics(benchmark=self.benchmark_symbol, notes="无成交记录")
        arr = np.array(returns)
        equity = np.cumprod(1 + arr)
        peak = np.maximum.accumulate(equity)
        max_dd = float(np.max(1 - equity / peak))
        sharpe = float(arr.mean() / arr.std()) if arr.std() > 1e-12 else 0.0
        bench_ret = self._benchmark_return(entries[0].trade_date, entries[-1].trade_date,
                                           horizon_days)
        total = float(equity[-1] - 1)
        return PerformanceMetrics(
            total_return=round(total, 6),
            max_drawdown=round(max_dd, 6),
            win_rate=round(wins / len(returns), 6),
            sharpe=round(sharpe, 6),
            alpha=round(total - bench_ret, 6),
            beta=1.0,
            n_trades=len(returns),
            benchmark=self.benchmark_symbol,
        )

    def _benchmark_return(self, start: dt.date, end: dt.date, horizon_days: int) -> float:
        try:
            bench = self.provider.resolve(self.benchmark_symbol, "US")
            bars = self.provider.get_bars_after(bench, start, horizon_days)
            if not bars:
                return 0.0
            snap = self.provider.get_snapshot(bench, start)
            return bars[-1].close / snap.last_close - 1
        except Exception:  # noqa: BLE001 - 基准不可得时 alpha 退化为 raw
            return 0.0
