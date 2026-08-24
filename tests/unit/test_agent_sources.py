"""Tests for data-source selection (stock + news) and the news-aware provider."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pandas as pd

from quant_platform.agents_bridge import sources as src
from quant_platform.agents_bridge.provider import DataFrameProvider
from trading_agents.data.base import DataProvider
from trading_agents.data.eastmoney import EastMoneyProvider
from trading_agents.schemas import MarketSnapshot, Ticker
from trading_agents.schemas.models import Market


class _FakeStock(DataProvider):
    name = "fake"

    def resolve(self, symbol: str, market: str) -> Ticker:
        return Ticker(symbol=symbol, market=Market(market))

    def get_snapshot(self, ticker, as_of_date, lookback_days=60):
        return MarketSnapshot(ticker=ticker, as_of_date=as_of_date, bars=[], last_close=1.0)

    def get_bars_after(self, ticker, start, days):
        return []


def test_fetch_news_filters_dedupes_and_caps(monkeypatch) -> None:
    monkeypatch.setattr(
        src,
        "_fetch_eastmoney",
        lambda symbol: [(dt.date(2024, 1, 2), "新闻A"), (dt.date(2024, 1, 9), "未来新闻")],
    )
    monkeypatch.setattr(
        src,
        "_fetch_cls",
        lambda symbol: [(dt.date(2024, 1, 3), "新闻A"), (None, "无日期新闻")],
    )

    result = src.fetch_news(("eastmoney", "cls"), "600519.SH", dt.date(2024, 1, 5))

    assert "新闻A" in result
    assert "无日期新闻" in result
    assert "未来新闻" not in result
    assert len(result) == 2


def test_fetch_news_swallows_fetch_errors(monkeypatch) -> None:
    def _boom(symbol):
        raise RuntimeError("network down")

    monkeypatch.setattr(src, "_fetch_eastmoney", _boom)
    monkeypatch.setattr(src, "_fetch_cls", lambda symbol: [(dt.date(2024, 1, 2), "财联社新闻")])

    result = src.fetch_news(("eastmoney", "cls"), "600519.SH", dt.date(2024, 1, 5))

    assert result == ["财联社新闻"]


def test_news_aware_provider_injects_news(monkeypatch) -> None:
    provider = src.NewsAwareProvider(_FakeStock(), ("eastmoney", "cls"))
    monkeypatch.setattr(src, "fetch_news", lambda sources, symbol, as_of: ["新闻1", "新闻2"])

    snapshot = provider.get_snapshot(
        Ticker(symbol="600519.SH", market=Market.CN), dt.date(2024, 1, 5)
    )

    assert snapshot.news == ["新闻1", "新闻2"]
    assert provider.name == "fake"


def test_runner_builds_stock_provider_by_source(tmp_path: Path) -> None:
    from quant_platform.agents_bridge.runner import AgentRunner

    history = pd.DataFrame(
        columns=["trade_date", "raw_open", "raw_high", "raw_low", "raw_close", "volume"]
    )
    runner = AgentRunner.__new__(AgentRunner)
    runner.cache_dir = tmp_path
    runner.stock_source = "local"
    assert isinstance(runner._build_stock_provider("600519.SH", history), DataFrameProvider)

    runner.stock_source = "eastmoney"
    assert isinstance(runner._build_stock_provider("600519.SH", history), EastMoneyProvider)


def test_agent_runner_battle_returns_text(tmp_path: Path) -> None:
    from quant_platform.agents_bridge.runner import AgentRunner

    runner = AgentRunner(
        llm_provider="mock", base_dir=tmp_path / "runs", cache_dir=tmp_path / "cache"
    )
    reply = runner.battle("标的: 600519.SH\n最终决策: hold", "我不同意，这只票要涨")
    assert isinstance(reply, str)
    assert reply.strip()
