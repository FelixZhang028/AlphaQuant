"""数据来源：股票行情来源 + 新闻来源，以及"行情+新闻"组合 Provider。

- 行情来源：本地 Parquet（离线）、东方财富（实时）、yfinance（美股）。
- 新闻来源：东方财富个股新闻、财联社电报、东方财富全球快讯。
- 新闻是"增强"输入而非"必需"：任一来源抓取失败都降级为空列表并告警，绝不阻塞分析。
"""

from __future__ import annotations

import datetime as dt
import logging
import re

import pandas as pd

from trading_agents.data.base import DataProvider
from trading_agents.schemas import MarketSnapshot, Ticker

log = logging.getLogger(__name__)

_MAX_NEWS_ITEMS = 12
_MAX_TEXT_LEN = 240

STOCK_SOURCES: dict[str, str] = {
    "local": "本地行情（Parquet，离线）",
    "akshare": "AkShare（实时）",
    "tonghuashun": "同花顺（实时）",
    "eastmoney": "东方财富（实时）",
    "yfinance": "yfinance（美股）",
}

NEWS_SOURCES: dict[str, str] = {
    "eastmoney": "东方财富个股新闻",
    "cls": "财联社电报",
    "global_em": "东方财富全球快讯",
}


def _six_digit(symbol: str) -> str:
    match = re.search(r"\d{6}", symbol)
    return match.group(0) if match else symbol


def _pick_column(frame: pd.DataFrame, keywords: tuple[str, ...]) -> str | None:
    for column in frame.columns:
        if any(keyword in str(column) for keyword in keywords):
            return str(column)
    return None


def _to_date(value: object) -> dt.date | None:
    if value is None:
        return None
    try:
        timestamp = pd.Timestamp(value)
        return None if pd.isna(timestamp) else timestamp.date()
    except (ValueError, TypeError):
        return None


def _extract_items(
    frame: pd.DataFrame,
    *,
    title_keywords: tuple[str, ...],
    content_keywords: tuple[str, ...],
    date_keywords: tuple[str, ...],
) -> list[tuple[dt.date | None, str]]:
    if frame is None or frame.empty:
        return []
    title_col = _pick_column(frame, title_keywords)
    content_col = _pick_column(frame, content_keywords)
    date_col = _pick_column(frame, date_keywords)
    items: list[tuple[dt.date | None, str]] = []
    for _, row in frame.iterrows():
        title = str(row[title_col]) if title_col else ""
        content = str(row[content_col]) if content_col else ""
        text = " ".join(part for part in (title, content) if part and part.lower() != "nan").strip()
        if text:
            items.append((_to_date(row[date_col]) if date_col else None, text))
    return items


def _fetch_eastmoney(symbol: str) -> list[tuple[dt.date | None, str]]:
    import akshare as ak

    frame = ak.stock_news_em(symbol=_six_digit(symbol))
    return _extract_items(
        frame,
        title_keywords=("标题", "title"),
        content_keywords=("内容", "content"),
        date_keywords=("时间", "日期", "date"),
    )


def _fetch_cls(symbol: str) -> list[tuple[dt.date | None, str]]:
    import akshare as ak

    frame = ak.stock_info_global_cls(symbol="全部")
    return _extract_items(
        frame,
        title_keywords=("标题", "title"),
        content_keywords=("内容", "content", "摘要"),
        date_keywords=("时间", "日期", "date"),
    )


def _fetch_global_em(symbol: str) -> list[tuple[dt.date | None, str]]:
    import akshare as ak

    frame = ak.stock_info_global_em()
    return _extract_items(
        frame,
        title_keywords=("标题", "title"),
        content_keywords=("摘要", "内容", "content"),
        date_keywords=("时间", "日期", "date"),
    )


def fetch_news(
    sources: tuple[str, ...], symbol: str, as_of_date: dt.date
) -> list[str]:
    """抓取并清洗新闻为注入快照的标题/摘要列表；失败来源降级为空。"""
    raw: list[tuple[dt.date | None, str]] = []
    for source in sources:
        fetcher = {
            "eastmoney": _fetch_eastmoney,
            "cls": _fetch_cls,
            "global_em": _fetch_global_em,
        }.get(source)
        if fetcher is None:
            continue
        try:
            raw.extend(fetcher(symbol))
        except Exception as exc:  # noqa: BLE001 - 新闻失败不阻塞
            log.warning("新闻来源 %s 抓取失败（降级为空）: %s", source, exc)

    cleaned: list[str] = []
    seen: set[str] = set()
    ordered = sorted(raw, key=lambda item: (item[0] is None, item[0] or dt.date.min), reverse=True)
    for item_date, text in ordered:
        if item_date is not None and item_date > as_of_date:
            continue
        text = " ".join(text.split())[:_MAX_TEXT_LEN]
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
        if len(cleaned) >= _MAX_NEWS_ITEMS:
            break
    return cleaned


class NewsAwareProvider(DataProvider):
    """组合 Provider：行情来自 stock 子源，新闻按所选来源注入快照。"""

    def __init__(self, stock: DataProvider, news_sources: tuple[str, ...] = ()) -> None:
        self.stock = stock
        self.news_sources = tuple(news_sources)
        self.name = stock.name

    def resolve(self, symbol: str, market: str) -> Ticker:
        return self.stock.resolve(symbol, market)

    def get_snapshot(
        self, ticker: Ticker, as_of_date: dt.date, lookback_days: int = 60
    ) -> MarketSnapshot:
        snapshot = self.stock.get_snapshot(ticker, as_of_date, lookback_days)
        if self.news_sources:
            snapshot.news = fetch_news(self.news_sources, ticker.symbol, as_of_date)
        return snapshot

    def get_bars_after(self, ticker: Ticker, start: dt.date, days: int) -> list:
        return self.stock.get_bars_after(ticker, start, days)
