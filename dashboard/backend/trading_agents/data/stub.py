"""StubDataProvider：确定性合成数据的离线数据源（测试/演示用，无网络）。

价格序列由 ``hash(symbol)`` 播种的确定性随机游走生成，相同输入恒定输出。
"""

from __future__ import annotations

import datetime as dt
import hashlib

import numpy as np

from trading_agents.data.base import DataProvider
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market


class StubDataProvider(DataProvider):
    """确定性 stub 数据源。"""

    name = "stub"

    def __init__(self, base_price: float = 100.0, daily_vol: float = 0.02) -> None:
        self.base_price = base_price
        self.daily_vol = daily_vol

    def _rng(self, symbol: str) -> np.random.Generator:
        seed = int(hashlib.sha256(symbol.encode()).hexdigest()[:8], 16)
        return np.random.default_rng(seed)

    def _series(self, symbol: str, end: dt.date, n: int) -> list[OHLCVBar]:
        """生成截至 end（含）的 n 个交易日序列（跳过周末，升序）。"""
        dates: list[dt.date] = []
        d = end
        while len(dates) < n:
            if d.weekday() < 5:
                dates.append(d)
            d -= dt.timedelta(days=1)
        dates.reverse()
        rng = self._rng(symbol)
        rets = rng.normal(0.0005, self.daily_vol, size=n)
        closes = self.base_price * np.exp(np.cumsum(rets))
        bars: list[OHLCVBar] = []
        for i, day in enumerate(dates):
            c = float(closes[i])
            o = c * float(1 + rng.normal(0, 0.005))
            hi, lo = max(o, c) * 1.005, min(o, c) * 0.995
            vol = int(abs(rng.normal(1_000_000, 200_000)))
            bars.append(
                OHLCVBar(date=day, open=round(o, 4), high=round(hi, 4),
                         low=round(lo, 4), close=round(c, 4), volume=vol)
            )
        return bars

    def resolve(self, symbol: str, market: str) -> Ticker:
        return Ticker(
            symbol=symbol.upper(),
            market=Market(market),
            name=f"{symbol.upper()} (stub)",
            industry="stub-industry",
            currency="USD" if market == "US" else "CNY",
        )

    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        bars = self._series(ticker.symbol, as_of_date, lookback_days)
        bars = [b for b in bars if b.date <= as_of_date]  # 快照语义：不越界
        if not bars:
            raise RuntimeError(f"stub: no bars available up to {as_of_date}")
        last = bars[-1]
        prev = bars[-2].close if len(bars) > 1 else last.close
        return MarketSnapshot(
            ticker=ticker,
            as_of_date=as_of_date,
            bars=bars,
            last_close=last.close,
            market_cap=last.close * 1e9,
            index="STUB-INDEX",
            fundamentals={
                "pe_ratio": 25.0,
                "revenue_yoy": 0.08,
                "prev_close": round(prev, 4),
            },
            news=[
                f"[stub] {ticker.symbol} 发布季度财报，营收符合预期（{as_of_date}）",
                f"[stub] 行业动态：{ticker.industry} 板块成交活跃",
            ],
        )

    def get_bars_after(
        self, ticker: Ticker, start: dt.date, days: int
    ) -> list[OHLCVBar]:
        end = start + dt.timedelta(days=days * 2 + 10)
        bars = self._series(ticker.symbol, end, days * 2 + 20)
        return [b for b in bars if b.date > start][:days]
