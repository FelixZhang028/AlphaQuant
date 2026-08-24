"""Tests for the expert prior-knowledge store and prompt injection."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from trading_agents.agents.analysts import snapshot_context
from trading_agents.schemas import MarketSnapshot, OHLCVBar, Ticker
from trading_agents.schemas.models import Market


def _snapshot(prior: str = "") -> MarketSnapshot:
    bars = [
        OHLCVBar(date=date(2024, 1, d), open=10, high=11, low=9, close=10.5, volume=1000)
        for d in range(2, 8)
    ]
    return MarketSnapshot(
        ticker=Ticker(symbol="600519.SH", market=Market.CN, name="贵州茅台"),
        as_of_date=date(2024, 1, 7),
        bars=bars,
        last_close=10.5,
        prior_knowledge=prior,
    )


def test_store_add_list_delete_render(tmp_path: Path) -> None:
    store = PriorKnowledgeStore(tmp_path / "prior.json")
    store.add("近期有大额解禁压力", "我的观点")
    store.add("行业政策收紧", "网页链接")

    entries = store.list()
    assert len(entries) == 2
    rendered = store.render()
    assert "解禁" in rendered and "政策" in rendered

    store.delete(entries[0].id)
    assert len(store.list()) == 1


def test_store_rejects_empty_content(tmp_path: Path) -> None:
    store = PriorKnowledgeStore(tmp_path / "prior.json")
    with pytest.raises(ValueError):
        store.add("   ", "我的观点")


def test_snapshot_context_includes_prior_knowledge() -> None:
    context = snapshot_context(_snapshot(prior="该股有减持风险，谨慎看多"))

    assert "专家先验知识" in context
    assert "减持风险" in context


def test_snapshot_context_without_prior_knowledge() -> None:
    context = snapshot_context(_snapshot())

    assert "专家先验知识" not in context
