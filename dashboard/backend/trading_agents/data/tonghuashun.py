"""TonghuashunProvider：同花顺公开行情接口的 A 股数据源。

与东财互补的独立通道：走 ``d.10jqka.com.cn`` 日线接口（按年拉取）。
当东财被 RST/限流时提供真实数据兜底。

特性：
- 日线按年请求 ``v6/line/{hs|sh}_{code}/01/{year}.js``，``01``=不复权。
  经校准与腾讯前复权在近期一致（无除权区间等价），成交量单位为股。
- 名称取日线接口的 ``name`` 字段；失败时降级为代码本身（防 LLM 幻觉）。
- 行情写 SQLite 缓存；网络失败时缓存兜底，无缓存则明确抛错。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import requests

from trading_agents.data.base import DataProvider
from trading_agents.data.cache import BarCache
from trading_agents.data.cn_quote import extract_cn_code, is_shanghai, ths_symbol
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market
from trading_agents.utils import get_logger

log = get_logger(__name__)

_LINE_BASE = "http://d.10jqka.com.cn/v6/line/{ths}/{adj}/{year}.js"
_ADJ = "01"  # 01=不复权；02=前复权（02 与腾讯 qfq 数值不一致，故用 01）
_HEADERS = {
    "Referer": "http://quote.10jqka.com.cn/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
}


class TonghuashunProvider(DataProvider):
    """同花顺 A 股数据源。"""

    name = "tonghuashun"

    def __init__(self, cache: BarCache | None = None, cache_path: Path | None = None) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        if cache is None and cache_path is not None:
            cache = BarCache(cache_path)
        self.cache = cache

    # ------------------------------------------------------------ 接口 ----
    def resolve(self, symbol: str, market: str) -> Ticker:
        ths = ths_symbol(symbol)
        name = self._fetch_name(ths) or extract_cn_code(symbol) or symbol
        return Ticker(
            symbol=self._normalize_symbol(symbol),
            market=Market.CN,
            name=name,
            industry="",
            currency="CNY",
        )

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
                log.warning("同花顺行情下载失败，尝试缓存降级: %s", exc)
                if self.cache:
                    bars = self.cache.get(ticker.symbol, start, as_of_date)
                if not bars:
                    raise RuntimeError(
                        f"无法获取 {ticker.symbol} 行情：网络失败且无可用缓存"
                    ) from exc
        bars = [b for b in bars if b.date <= as_of_date]  # 快照语义
        if not bars:
            raise RuntimeError(f"no bars on or before {as_of_date} for {ticker.symbol}")
        prev_close = bars[-2].close if len(bars) > 1 else bars[-1].close
        return MarketSnapshot(
            ticker=ticker,
            as_of_date=as_of_date,
            bars=bars,
            last_close=bars[-1].close,
            market_cap=None,  # 同花顺实时接口无总市值字段，不虚造
            index="CSI300",
            fundamentals={"prev_close": prev_close},
            news=[],  # 同花顺新闻接口未接入，情绪/新闻分析师将明确标注无新闻输入
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

    # ------------------------------------------------------------ 内部 ----
    def _download_bars(self, symbol: str, start: dt.date, end: dt.date) -> list[OHLCVBar]:
        ths = ths_symbol(symbol)
        bars: list[OHLCVBar] = []
        for year in range(start.year, end.year + 1):
            bars.extend(self._fetch_year(ths, year))
        bars = [b for b in bars if start <= b.date <= end]
        if not bars:
            raise RuntimeError(
                f"tonghuashun returned no bars in [{start}, {end}] for {symbol}"
            )
        return bars

    def _fetch_year(self, ths: str, year: int) -> list[OHLCVBar]:
        url = _LINE_BASE.format(ths=ths, adj=_ADJ, year=year)
        r = self._session.get(url, timeout=10)
        r.raise_for_status()
        text = r.text
        lpar, rpar = text.find("("), text.rfind(")")
        if lpar < 0 or rpar <= lpar:
            raise RuntimeError(f"ths {year} payload: unexpected for {ths}")
        payload = json.loads(text[lpar + 1: rpar])
        data = payload.get("data") or ""
        bars: list[OHLCVBar] = []
        for line in data.split(";"):
            if not line:
                continue
            # 格式: date,open,high,low,close,volume,amount,turnover,,,0
            parts = line.split(",")
            if len(parts) < 6:
                continue
            day = dt.date.fromisoformat(f"{parts[0][:4]}-{parts[0][4:6]}-{parts[0][6:8]}")
            bars.append(
                OHLCVBar(
                    date=day, open=float(parts[1]), high=float(parts[2]),
                    low=float(parts[3]), close=float(parts[4]),
                    volume=int(float(parts[5])),
                )
            )
        return bars

    def _fetch_name(self, ths: str) -> str | None:
        """从同花顺日线接口取标的名称（last60.js 带 name 字段）。"""
        for adj in ("01", "02"):
            url = _LINE_BASE.format(ths=ths, adj=adj, year="last60")
            try:
                r = self._session.get(url, timeout=8)
                r.raise_for_status()
                text = r.text
                lpar, rpar = text.find("("), text.rfind(")")
                if lpar < 0 or rpar <= lpar:
                    continue
                payload = json.loads(text[lpar + 1: rpar])
                name = payload.get("name")
                if name:
                    return str(name)
            except Exception as exc:  # noqa: BLE001
                log.debug("同花顺名称获取失败: %s", exc)
        return None

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        code = extract_cn_code(symbol)
        if not code:
            return symbol.upper()
        return f"{code}.{'SS' if is_shanghai(code) else 'SZ'}"
