"""数据层：DataProvider 接口、多数据源实现、SQLite 缓存与快照校验。

数据源矩阵（A 股）：
- ``eastmoney``：东方财富直连（HTTP/HTTPS/代理多通道回退 + 新浪兜底）。
- ``akshare``：akshare 库（腾讯 → 新浪 → 东财端点内回退）。
- ``tonghuashun``：同花顺 d.10jqka.com.cn 日线接口。
- ``auto``：FallbackProvider 组合，按 eastmoney → akshare → tonghuashun 降级。
"""

from trading_agents.data.base import (
    DataProvider,
    LookAheadError,
    validate_snapshot,
)
from trading_agents.data.fallback import FallbackProvider
from trading_agents.data.stub import StubDataProvider

__all__ = [
    "DataProvider",
    "FallbackProvider",
    "LookAheadError",
    "StubDataProvider",
    "validate_snapshot",
]
