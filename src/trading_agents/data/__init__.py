"""数据层：DataProvider 接口、Stub/YFinance 实现、SQLite 缓存与快照校验。"""

from trading_agents.data.base import (
    DataProvider,
    LookAheadError,
    validate_snapshot,
)
from trading_agents.data.stub import StubDataProvider

__all__ = ["DataProvider", "LookAheadError", "StubDataProvider", "validate_snapshot"]
