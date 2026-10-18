"""回测与绩效评估：对已产生的历史决策序列做行情回放（机制 M5/M10）。

回测规则与模拟执行规则一致（同一 SimulatedExchange 滑点/手续费/T+1），
口径不一致视为 bug。
"""

from trading_agents.backtest.replay import Backtester

__all__ = ["Backtester"]
