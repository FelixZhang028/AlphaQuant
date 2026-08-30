"""LLM 多智能体框架与 FellowQuant 回测平台的桥接层。

将 FellowQuant 的日线 DataFrame 适配成 trading_agents 的数据协议，
并把流水线的最终决策（Decision）映射为平台信号（Signal）。
"""

from quant_platform.agents_bridge.mapping import decision_to_signal
from quant_platform.agents_bridge.provider import DataFrameProvider
from quant_platform.agents_bridge.runner import AgentRunner

__all__ = ["AgentRunner", "DataFrameProvider", "decision_to_signal"]
