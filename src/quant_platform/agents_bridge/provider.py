"""DataFrame 行情适配器：把 AlphaQuant 日线数据喂给 LLM 多智能体流水线。

列名映射（AlphaQuant 日线 -> trading_agents OHLCVBar）：

- ``trade_date`` -> ``date``
- ``raw_open``  -> ``open``
- ``raw_high``  -> ``high``
- ``raw_low``   -> ``low``
- ``raw_close`` -> ``close``
- ``volume``    -> ``volume``（int 化）

注意：``name`` 必须为 ``"stub"``。pipeline 的 ``_node_fetch_data`` 在
provider 非 stub 且 ``get_snapshot`` 抛 ``RuntimeError`` 时会静默降级成
stub 假数据；本实现数据不足时抛 ``ValueError``（非 RuntimeError）作为双保险。
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from trading_agents.data.base import DataProvider
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market


class DataFrameProvider(DataProvider):
    """以内存 DataFrame 为数据源的 DataProvider（离线、确定性）。"""

    name = "stub"  # 防止 pipeline 把数据问题静默降级成 stub 假数据

    def __init__(
        self,
        bars: dict[str, pd.DataFrame],
        names: dict[str, str] | None = None,
    ) -> None:
        self._bars = {
            str(symbol): frame.sort_values("trade_date").reset_index(drop=True)
            for symbol, frame in bars.items()
        }
        self._names = {str(k): v for k, v in (names or {}).items()}

    def resolve(self, symbol: str, market: str) -> Ticker:
        """解析标的身份：名称取自 names 映射，缺省用代码本身。"""
        return Ticker(
            symbol=symbol,
            market=Market(market),
            name=self._names.get(symbol, symbol),
            currency="CNY" if market == "CN" else "USD",
        )

    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        """取 as_of_date 及之前的尾部 lookback_days 行构造快照。"""
        frame = self._frame_until(ticker.symbol, as_of_date).tail(lookback_days)
        if frame.empty:
            raise ValueError(
                f"{ticker.symbol} 在 {as_of_date} 及之前没有可用行情数据"
            )
        bars = self._to_bars(frame)
        return MarketSnapshot(
            ticker=ticker,
            as_of_date=as_of_date,
            bars=bars,
            last_close=bars[-1].close,
            market_cap=None,
            fundamentals={},
            news=[],
        )

    def get_bars_after(
        self, ticker: Ticker, start: dt.date, days: int
    ) -> list[OHLCVBar]:
        """取 start 之后（不含当天）的 days 行，用于记忆回填实现收益。"""
        frame = self._get(ticker.symbol)
        cutoff = pd.Timestamp(start)
        after = frame[pd.to_datetime(frame["trade_date"]) > cutoff].head(days)
        return self._to_bars(after)

    # ------------------------------------------------------------------ #
    def _get(self, symbol: str) -> pd.DataFrame:
        frame = self._bars.get(symbol)
        if frame is None:
            raise ValueError(f"没有标的 {symbol} 的行情数据")
        return frame

    def _frame_until(self, symbol: str, as_of_date: dt.date) -> pd.DataFrame:
        frame = self._get(symbol)
        cutoff = pd.Timestamp(as_of_date)
        return frame[pd.to_datetime(frame["trade_date"]) <= cutoff]

    @staticmethod
    def _to_bars(frame: pd.DataFrame) -> list[OHLCVBar]:
        bars: list[OHLCVBar] = []
        for row in frame.itertuples(index=False):
            bars.append(
                OHLCVBar(
                    date=pd.Timestamp(row.trade_date).date(),
                    open=float(row.raw_open),
                    high=float(row.raw_high),
                    low=float(row.raw_low),
                    close=float(row.raw_close),
                    volume=int(row.volume),
                )
            )
        return bars
