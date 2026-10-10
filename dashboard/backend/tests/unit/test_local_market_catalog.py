"""Local catalog scopes, quality evidence, caching and isolated single-stock updates."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant.market_catalog import LocalMarketCatalog
from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository


@pytest.fixture
def repo(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    sessions = pd.date_range("2026-01-05", "2026-01-09")
    repository.save_table("trade_calendar", pd.DataFrame({"cal_date": sessions, "is_open": 1}))
    repository.save_table("security_master", pd.DataFrame({
        "symbol": ["000001.SZ", "600519.SH", "300750.SZ"],
        "name": ["平安银行", "贵州茅台", "宁德时代"],
    }))
    bars = []
    for symbol, dates in [("000001.SZ", sessions[[0, 1, 4]]), ("600519.SH", sessions),
                          ("300750.SZ", sessions[[0, 4]]), ("688001.SH", sessions)]:
        for day in dates:
            bars.append({"symbol": symbol, "trade_date": day,
                         "quality_status": "UNKNOWN" if symbol == "300750.SZ" else "OK", "raw_close": 10.0})
    repository.save_table("daily_bars", pd.DataFrame(bars))
    return repository


def test_all_downloaded_is_not_limited_to_universe_and_has_names(repo):
    result = LocalMarketCatalog(repo.root).page(["000001", "000002"])
    assert result["total"] == result["downloaded_count"] == 4
    assert result["universe_count"] == 2 and result["universe_downloaded_count"] == 1
    rows = {row["symbol"]: row for row in result["items"]}
    assert rows["600519"]["name"] == "贵州茅台" and not rows["600519"]["in_universe"]
    assert rows["688001"]["name"] == "名称待补充"
    assert rows["600519"]["status"] == "COMPLETE"
    assert rows["000001"]["status"] == "GAPS"
    assert rows["300750"]["status"] == "CHECK"


def test_universe_scope_includes_undownloaded_and_empty_pool_stays_empty(repo):
    result = LocalMarketCatalog(repo.root).page(["000001", "000002"], scope="universe")
    assert result["total"] == 2
    assert result["items"][1]["status"] == "NO_DATA"
    assert LocalMarketCatalog(repo.root).page([], scope="universe")["items"] == []


def test_search_names_codes_literal_characters_and_page_bounds(repo):
    catalog = LocalMarketCatalog(repo.root)
    assert catalog.page([], q="茅台")["items"][0]["symbol"] == "600519"
    assert catalog.page([], q="0000")["items"][0]["symbol"] == "000001"
    assert catalog.page([], q=".*")["total"] == 0
    assert catalog.page([], page_size=2)["pages"] == 2
    assert catalog.page([], page=999, page_size=2)["page"] == 2
    assert len(catalog.page([], page=2, page_size=2)["items"]) == 2


def test_detail_identifies_actual_missing_trading_range(repo):
    row = LocalMarketCatalog(repo.root).detail("000001", ["000001"])
    assert row["rows"] == 3 and row["coverage"] == .6 and row["missing_rows"] == 2
    assert row["missing_ranges"] == [{"start_date": "2026-01-07", "end_date": "2026-01-08", "days": 2}]
    assert LocalMarketCatalog(repo.root).detail("000002", ["000002"])["status"] == "NO_DATA"
    with pytest.raises(KeyError):
        LocalMarketCatalog(repo.root).detail("000003", [])


def test_search_and_pagination_reuse_index_and_writes_invalidate_it(repo, monkeypatch):
    first = LocalMarketCatalog(repo.root)
    from app.quant import market_catalog
    original = market_catalog._read_columns
    read = Mock(wraps=original)
    monkeypatch.setattr(market_catalog, "_read_columns", read)
    LocalMarketCatalog(repo.root).page([], q="银行", page_size=1)
    assert read.call_count == 0
    repo.save_table("daily_bars", pd.DataFrame([{
        "symbol": "000002.SZ", "trade_date": pd.Timestamp("2026-01-09"), "quality_status": "OK"}]))
    assert LocalMarketCatalog(repo.root).page([])["downloaded_count"] == first.page([])["downloaded_count"] + 1
    assert read.call_count > 0


def test_missing_calendar_never_claims_complete(repo):
    (repo.root / "trade_calendar.parquet").unlink()
    row = LocalMarketCatalog(repo.root).detail("600519", [])
    assert row["coverage"] is None and row["status"] == "CHECK"


def test_disk_summary_survives_restart_without_rescanning_prices(repo, monkeypatch):
    from app.quant import market_catalog
    before = LocalMarketCatalog(repo.root).page([])
    market_catalog._index.cache_clear()
    read = Mock(side_effect=AssertionError("cached summary must not reread parquet"))
    monkeypatch.setattr(market_catalog, "_read_columns", read)
    assert LocalMarketCatalog(repo.root).page([]) == before
    read.assert_not_called()


def test_nontrading_dates_cannot_hide_missing_sessions(repo):
    path = repo.root / "daily_bars/year=2026/data.parquet"
    bars = pd.read_parquet(path)
    bars.loc[(bars.symbol == "600519.SH") & (bars.trade_date == pd.Timestamp("2026-01-07")), "trade_date"] = pd.Timestamp("2026-01-10")
    bars.to_parquet(path, index=False)
    # Extend the calendar beyond the last bar, but the Saturday itself is closed.
    repo.save_table("trade_calendar", pd.DataFrame({"cal_date": pd.to_datetime(["2026-01-10", "2026-01-12"]), "is_open": [0, 1]}))
    row = LocalMarketCatalog(repo.root).detail("600519", [])
    assert row["status"] == "CHECK" and row["unexpected_rows"] == 1
    assert row["missing_rows"] == 1 and row["coverage"] == .8


@pytest.fixture
def client(repo, monkeypatch):
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 123}
    monkeypatch.setattr(workspace, "market_repository", lambda: repo)
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda _: ["000001", "000002"])
    with TestClient(app) as test_client:
        yield test_client


def test_catalog_routes_and_validation(client):
    response = client.get("/api/v1/data-center/market", params={"q": "茅台", "page_size": 1})
    assert response.status_code == 200 and response.json()["total"] == 1
    assert client.get("/api/v1/data-center/market/000001").json()["missing_rows"] == 2
    assert client.get("/api/v1/data-center/market/000003").status_code == 404
    for params in [{"page": 0}, {"page_size": 101}, {"scope": "wrong"}]:
        assert client.get("/api/v1/data-center/market", params=params).status_code == 422


def test_single_stock_update_never_downloads_the_whole_pool_or_changes_it(client, monkeypatch):
    service = Mock()
    service.update_market_data.return_value = SimpleNamespace(status="SUCCESS", message="完成", rows=5, version_id="test-version")
    monkeypatch.setattr(workspace, "build_data_center_service", lambda _: service)
    save_pool = Mock()
    monkeypatch.setattr(workspace, "_save_universe", save_pool)
    response = client.post("/api/v1/data-center/market/600519/update", json={"start_date": "2026-01-05", "end_date": "2026-01-09"})
    assert response.status_code == 200 and response.json()["status"] == "SUCCESS"
    service.update_market_data.assert_called_once_with(date(2026, 1, 5), date(2026, 1, 9), symbols=["600519.SH"])
    save_pool.assert_not_called()
    for symbol, body in [("oops", {"start_date": "2026-01-05", "end_date": "2026-01-09"}),
                         ("600519", {"start_date": "2026-01-09", "end_date": "2026-01-05"})]:
        assert client.post(f"/api/v1/data-center/market/{symbol}/update", json=body).status_code == 422
    assert service.update_market_data.call_count == 1


def test_catalog_requires_login():
    app = FastAPI()
    app.include_router(workspace.router)
    with TestClient(app) as client:
        assert client.get("/api/v1/data-center/market").status_code == 401
