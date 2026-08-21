"""DataProvider 接口与快照语义校验（机制 M8：防未来函数）。

任何下游不得越界使用分析日期之后的数据：
:func:`validate_snapshot` 在 ``snapshot.as_of_date > trade_date`` 时抛
:class:`LookAheadError`。
"""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod

from trading_agents.schemas import MarketSnapshot, Ticker


class LookAheadError(RuntimeError):
    """数据快照截止日期越过分析日期（未来函数）。"""


def validate_snapshot(snapshot: MarketSnapshot, trade_date: dt.date) -> MarketSnapshot:
    """校验快照不越界；越界直接报错，不允许静默使用。"""
    if snapshot.as_of_date > trade_date:
        raise LookAheadError(
            f"snapshot as_of_date {snapshot.as_of_date} is after trade_date {trade_date}: "
            "look-ahead data is forbidden"
        )
    bad = [b.date for b in snapshot.bars if b.date > trade_date]
    if bad:
        raise LookAheadError(
            f"snapshot contains {len(bad)} bars after trade_date {trade_date} (first: {bad[0]})"
        )
    return snapshot


class DataProvider(ABC):
    """数据源接口：输入 ticker 与分析日期，输出带 as_of_date 的快照。

    实现方必须保证快照只含 ``as_of_date`` 当天及之前的数据。
    数据访问失败时明确抛错，不允许静默返回空数据。
    """

    name: str = "abstract"

    @abstractmethod
    def resolve(self, symbol: str, market: str) -> Ticker:
        """解析标的身份（名称/行业/货币）。"""

    @abstractmethod
    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        """构建截至 as_of_date 的已验证数据快照。"""

    @abstractmethod
    def get_bars_after(
        self, ticker: Ticker, start: dt.date, days: int
    ) -> list:
        """取 start 之后的行情（用于记忆回填实现收益/回测回放）。"""
