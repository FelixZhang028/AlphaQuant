"""YFinanceProvider：基于 yfinance 的美股数据源（可选依赖）。

- yfinance 未安装时，构造即明确报错并提示降级到 stub。
- 所有请求先查 SQLite 缓存；网络失败时若缓存覆盖目标区间则降级用缓存，
  否则明确抛错，绝不静默返回空数据。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from trading_agents.data.base import DataProvider
from trading_agents.data.cache import BarCache
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market
from trading_agents.utils import get_logger

log = get_logger(__name__)


class YFinanceProvider(DataProvider):
    name = "yfinance"

    def __init__(
        self,
        cache: BarCache | None = None,
        cache_path: Path | None = None,
        proxy: str | None = None,
    ) -> None:
        try:
            import yfinance as yf  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "yfinance 未安装，无法使用真实行情数据源。"
                "请 `pip install yfinance`，或使用 stub 数据源离线运行。"
            ) from exc
        # yfinance>=1.x 的 curl_cffi 会话不读系统代理，且每次请求会用
        # YfConfig.network.proxy 覆盖 session 上的代理设置，因此必须通过
        # set_config 全局注入；旧版本（requests 实现）则回退到环境变量。
        if proxy:
            if hasattr(yf, "config") and hasattr(yf.config, "network"):
                yf.config.network.proxy = proxy
            elif hasattr(yf, "set_config"):  # pragma: no cover - 过渡版本
                yf.set_config(proxy=proxy)
            else:  # pragma: no cover - 旧版本 yfinance（requests 实现）
                import os

                os.environ.setdefault("HTTPS_PROXY", proxy)
                os.environ.setdefault("HTTP_PROXY", proxy)
            log.info("yfinance 使用代理: %s", proxy)
        self._yf = yf
        if cache is None and cache_path is not None:
            cache = BarCache(cache_path)
        self.cache = cache

    def resolve(self, symbol: str, market: str) -> Ticker:
        symbol = symbol.upper()
        try:
            info = self._yf.Ticker(symbol).info
            return Ticker(
                symbol=symbol,
                market=Market(market),
                name=info.get("shortName", symbol),
                industry=info.get("industry", ""),
                currency=info.get("currency", "USD"),
            )
        except Exception as exc:  # noqa: BLE001 - 网络失败降级为最小身份
            log.warning("resolve(%s) 网络失败，降级为最小身份: %s", symbol, exc)
            return Ticker(symbol=symbol, market=Market(market), name=symbol)

    def _download_bars(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        df = self._yf.download(
            symbol, start=start.isoformat(), end=(end + dt.timedelta(days=1)).isoformat(),
            progress=False, auto_adjust=True,
        )
        if df is None or df.empty:
            raise RuntimeError(f"yfinance returned no data for {symbol} in [{start}, {end}]")
        bars: list[OHLCVBar] = []
        for idx, row in df.iterrows():
            day = idx.date() if hasattr(idx, "date") else dt.date.fromisoformat(str(idx)[:10])
            def _v(x: object) -> float:
                return float(x.iloc[0]) if hasattr(x, "iloc") else float(x)  # type: ignore[arg-type]
            bars.append(
                OHLCVBar(
                    date=day, open=_v(row["Open"]), high=_v(row["High"]),
                    low=_v(row["Low"]), close=_v(row["Close"]), volume=int(_v(row["Volume"])),
                )
            )
        return bars

    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        start = as_of_date - dt.timedelta(days=int(lookback_days * 1.6) + 10)
        bars: list[OHLCVBar] = []
        if self.cache and self.cache.covers(ticker.symbol, start, as_of_date):
            bars = self.cache.get(ticker.symbol, start, as_of_date)
        if not bars:
            try:
                bars = self._download_bars(ticker.symbol, start, as_of_date)
                if self.cache:
                    self.cache.put(ticker.symbol, bars)
            except Exception as exc:  # noqa: BLE001 - 网络失败降级缓存
                log.warning("行情下载失败，尝试缓存降级: %s", exc)
                if self.cache:
                    bars = self.cache.get(ticker.symbol, start, as_of_date)
                if not bars:
                    raise RuntimeError(
                        f"无法获取 {ticker.symbol} 行情：网络失败且无可用缓存"
                    ) from exc
        bars = [b for b in bars if b.date <= as_of_date]  # 快照语义
        if not bars:
            raise RuntimeError(f"no bars on or before {as_of_date} for {ticker.symbol}")
        news: list[str] = []
        try:
            for item in (self._yf.Ticker(ticker.symbol).news or [])[:10]:
                title = item.get("content", {}).get("title") or item.get("title", "")
                if title:
                    news.append(str(title))
        except Exception as exc:  # noqa: BLE001
            log.warning("新闻拉取失败（降级为空列表）: %s", exc)
        return MarketSnapshot(
            ticker=ticker,
            as_of_date=as_of_date,
            bars=bars,
            last_close=bars[-1].close,
            index="SPX",
            fundamentals={},
            news=news,
        )

    def get_bars_after(self, ticker: Ticker, start: dt.date, days: int) -> list[OHLCVBar]:
        end = start + dt.timedelta(days=days * 2 + 10)
        bars: list[OHLCVBar] = []
        if self.cache:
            bars = self.cache.get(ticker.symbol, start, end)
        if not bars:
            bars = self._download_bars(ticker.symbol, start, end)
            if self.cache:
                self.cache.put(ticker.symbol, bars)
        return [b for b in bars if b.date > start][:days]
