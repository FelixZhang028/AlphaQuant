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


def test_kline_adjusts_to_latest_bar_and_hides_suspended_sessions(repo):
    repo.save_table("daily_bars", pd.DataFrame({
        "symbol": "000002.SZ", "trade_date": pd.date_range("2026-01-05", "2026-01-08"), "quality_status": "OK",
        "raw_open": [20.0, 20.0, 10.0, 11.0], "raw_high": [22.0, 20.0, 11.0, 12.0],
        "raw_low": [19.0, 20.0, 9.0, 10.0], "raw_close": [20.0, 20.0, 10.0, 12.0],
        "volume": [100.0, 0.0, 300.0, 400.0], "adj_factor": [0.5, 0.5, 1.0, 1.0],
        "is_suspended": [False, True, False, False]}))
    forward = LocalMarketCatalog(repo.root).kline("000002")
    assert forward["adjust"] == "forward" and forward["suspended_days"] == 1 and forward["invalid_rows"] == 0
    assert [bar["date"] for bar in forward["bars"]] == ["2026-01-05", "2026-01-07", "2026-01-08"]
    assert forward["bars"][0] == {"date": "2026-01-05", "open": 10.0, "high": 11.0, "low": 9.5, "close": 10.0, "volume": 100, "factor": 0.5}
    assert forward["bars"][-1]["close"] == 12.0 and forward["end_date"] == "2026-01-08"
    raw = LocalMarketCatalog(repo.root).kline("000002", adjust="none")["bars"][0]
    assert raw["open"] == 20.0 and raw["factor"] == 1.0


def test_kline_never_draws_incomplete_prices_or_invents_adjustment(repo):
    # The shared fixture stores closes only: no candle can be drawn and no factor exists.
    result = LocalMarketCatalog(repo.root).kline("600519")
    assert result["bars"] == [] and result["invalid_rows"] == 5 and result["start_date"] is None
    assert result["adjust"] == "none"
    with pytest.raises(KeyError):
        LocalMarketCatalog(repo.root).kline("000002")


def save_index_bars(repo):
    repo.save_table("benchmark_bars", pd.DataFrame({
        "symbol": ["000001.SH"] * 3 + ["399006.SZ"],
        "trade_date": pd.to_datetime(["2026-01-07", "2026-01-05", "2026-01-06", "2026-01-05"]),
        "raw_open": [3010.0, 3000.0, 3005.0, 2000.0], "raw_high": [3030.0, 3020.0, None, 2010.0],
        "raw_low": [3000.0, 2990.0, 2995.0, 1990.0], "raw_close": [3025.0, 3010.0, 3000.0, 2005.0],
        "volume": [3e10, 2e10, 2.5e10, 1e10], "quality_status": "OK"}))


def test_index_kline_reads_index_bars_and_never_becomes_the_same_numbered_stock(repo):
    save_index_bars(repo)
    catalog = LocalMarketCatalog(repo.root)
    index = catalog.kline("000001.sh", adjust="forward")
    assert index["symbol"] == "000001.SH" and index["name"] == "上证指数" and index["kind"] == "index"
    assert index["adjust"] == "none" and index["suspended_days"] == 0 and index["invalid_rows"] == 1
    assert index["bars"] == [
        {"date": "2026-01-05", "open": 3000.0, "high": 3020.0, "low": 2990.0, "close": 3010.0, "volume": 20000000000, "factor": 1.0},
        {"date": "2026-01-07", "open": 3010.0, "high": 3030.0, "low": 3000.0, "close": 3025.0, "volume": 30000000000, "factor": 1.0}]
    # Without the suffix 000001 is still 平安银行.
    stock = catalog.kline("000001")
    assert stock["symbol"] == "000001" and stock["name"] == "平安银行" and stock["kind"] == "stock"
    with pytest.raises(KeyError):
        catalog.kline("000300.SH")


def test_index_list_follows_home_order_and_only_lists_local_indexes(repo):
    assert LocalMarketCatalog(repo.root).indexes() == []
    save_index_bars(repo)
    assert LocalMarketCatalog(repo.root).indexes() == [
        {"symbol": "000001.SH", "name": "上证指数"}, {"symbol": "399006.SZ", "name": "创业板指"}]


@pytest.fixture
def client(repo, monkeypatch):
    app = FastAPI()
    app.include_router(workspace.router)
    app.state.user = {"id": 123, "is_admin": False}
    app.dependency_overrides[get_current_user] = lambda: app.state.user
    monkeypatch.setattr(workspace, "market_repository", lambda: repo)
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda _: ["000001", "000002"])
    with TestClient(app) as test_client:
        yield test_client


def test_catalog_routes_and_validation(client):
    response = client.get("/api/v1/data-center/market", params={"q": "茅台", "page_size": 1})
    assert response.status_code == 200 and response.json()["total"] == 1
    assert client.get("/api/v1/data-center/market/000001").json()["missing_rows"] == 2
    assert client.get("/api/v1/data-center/market/000003").status_code == 404
    assert client.get("/api/v1/data-center/market/600519/bars").json()["symbol"] == "600519"
    assert client.get("/api/v1/data-center/market/000002/bars").status_code == 404
    assert client.get("/api/v1/data-center/market/600519/bars", params={"adjust": "backward"}).status_code == 422
    for params in [{"page": 0}, {"page_size": 101}, {"scope": "wrong"}]:
        assert client.get("/api/v1/data-center/market", params=params).status_code == 422


def test_routes_list_indexes_and_draw_them_by_full_code(client, repo):
    assert client.get("/api/v1/data-center/market").json()["indexes"] == []
    save_index_bars(repo)
    assert client.get("/api/v1/data-center/market").json()["indexes"][0] == {"symbol": "000001.SH", "name": "上证指数"}
    index = client.get("/api/v1/data-center/market/000001.SH/bars").json()
    assert index["kind"] == "index" and index["symbol"] == "000001.SH" and len(index["bars"]) == 2
    assert client.get("/api/v1/data-center/market/000001/bars").json()["kind"] == "stock"
    assert client.get("/api/v1/data-center/market/000300.SH/bars").status_code == 404


def test_single_stock_update_never_downloads_the_whole_pool_or_changes_it(client, monkeypatch):
    service = Mock()
    service.update_market_data.return_value = SimpleNamespace(status="SUCCESS", message="完成", rows=5, version_id="test-version")
    monkeypatch.setattr(workspace, "build_data_center_service", lambda _: service)
    save_pool = Mock()
    monkeypatch.setattr(workspace, "_save_universe", save_pool)
    # 下载数据只有管理员能做：普通用户的数据每天自动更新。
    body = {"start_date": "2026-01-05", "end_date": "2026-01-09"}
    assert client.post("/api/v1/data-center/market/600519/update", json=body).status_code == 403
    service.update_market_data.assert_not_called()
    client.app.state.user = {"id": 123, "is_admin": True}
    response = client.post("/api/v1/data-center/market/600519/update", json=body)
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
