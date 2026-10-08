"""FallbackProvider：多数据源组合降级链（A 股多源容错）。

按序尝试多个 ``DataProvider``，首个成功者胜出并缓存该结果；全部失败时
抛出最后一个错误（由流水线最终降级 stub）。单源网络抖动不再直接打穿到
stub，例如：eastmoney 被 RST → 自动切 akshare → 再切同花顺。
"""

from __future__ import annotations

import datetime as dt

from trading_agents.data.base import DataProvider
from trading_agents.schemas import MarketSnapshot, Ticker
from trading_agents.utils import get_logger

log = get_logger(__name__)


class FallbackProvider(DataProvider):
    """按序降级的组合数据源。``name`` 取 ``auto``（流水线据此判断是否可降级）。"""

    name = "auto"

    def __init__(self, providers: list[DataProvider]) -> None:
        if not providers:
            raise ValueError("FallbackProvider 需要至少一个数据源")
        self.providers = providers

    @property
    def active_source(self) -> str:
        return getattr(self, "_last_source", "")

    def _run(self, method: str, *args, **kwargs):
        last_exc: Exception | None = None
        for provider in self.providers:
            try:
                result = getattr(provider, method)(*args, **kwargs)
                self._last_source = provider.name
                log.info("数据源 %s 命中（%s）", provider.name, method)
                return result
            except Exception as exc:  # noqa: BLE001 - 单源失败继续降级
                last_exc = exc
                log.warning(
                    "数据源 %s 的 %s 失败，尝试下一数据源: %s",
                    provider.name, method, exc,
                )
        raise RuntimeError(
            f"所有数据源均失败（{', '.join(p.name for p in self.providers)}）: {last_exc}"
        ) from last_exc

    # ------------------------------------------------------------ 接口 ----
    def resolve(self, symbol: str, market: str) -> Ticker:
        return self._run("resolve", symbol, market)

    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        return self._run("get_snapshot", ticker, as_of_date, lookback_days=lookback_days)

    def get_bars_after(self, ticker: Ticker, start: dt.date, days: int) -> list:
        return self._run("get_bars_after", ticker, start, days)
