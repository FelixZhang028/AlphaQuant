"""Index constituents over time, and backtests that use an index as it was on each day."""
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant import markets
from app.routes import backtests
from app.routes.auth import get_current_user
from quant_platform.application import data_jobs
from quant_platform.application.backtest_service import BacktestService
from quant_platform.backtest.validity import assess_backtest_validity
from quant_platform.application.data_service import DataCenterService
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.index_constituents import (
    CHECKS_TABLE,
    CONSTITUENTS_TABLE,
    checked_range,
    members_on,
    membership,
    normalize_baostock_constituents,
    require_coverage,
    stored_lists,
    week_start,
)
from quant_platform.data.index_constituents_backfill import BaoStockIndexConstituentsBackfill
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.universe.historical import HistoricalUniverse

HS300, SZ50, ZZ500 = "000300.SH", "000016.SH", "000905.SH"
BACKEND = Path(__file__).resolve().parents[2]


def monday(text):
    day = date.fromisoformat(text)
    assert day.weekday() == 0
    return day


def lists_frame(index_symbol, lists):
    return pd.DataFrame([{"index_symbol": index_symbol, "effective_date": pd.Timestamp(monday(day)), "symbol": symbol}
                         for day, members in lists.items() for symbol in members])


def stay_rows(stays):
    """(symbol, first day, day of the first list without it or None) - plain values, the same on every pandas version."""
    day = lambda value: None if pd.isna(value) else value.date().isoformat()  # noqa: E731
    return [[symbol, day(start), day(end)] for symbol, start, end in
            zip(stays["symbol"], stays["effective_from"], stays["effective_to"])]


def test_a_vendor_list_becomes_one_dated_row_per_member():
    vendor = pd.DataFrame({"updateDate": "2025-06-16", "code": ["sh.600000", "sz.000001", "sz.000001"], "code_name": ["浦发银行", "平安银行", "平安银行"]})
    rows = normalize_baostock_constituents(vendor, HS300, monday("2025-06-16"))
    assert rows[["index_symbol", "symbol"]].values.tolist() == [[HS300, "000001.SZ"], [HS300, "600000.SH"]]
    assert rows["effective_date"].unique().tolist() == [pd.Timestamp("2025-06-16")]
    assert normalize_baostock_constituents(pd.DataFrame(), HS300, monday("2025-06-16")).empty
    assert week_start(date(2025, 6, 18)) == week_start(date(2025, 6, 22)) == monday("2025-06-16")


def test_membership_is_one_row_per_unbroken_stay():
    stored = lists_frame(HS300, {
        "2025-01-06": ["A", "B", "C"],
        "2025-06-16": ["A", "C", "D"],       # B 出，D 进
        "2025-09-01": ["A", "C", "D"],       # 多存的一份相同名单不会把成分期间切开
        "2025-12-15": ["A", "B", "D"],       # C 出，B 回来
    })
    stored = pd.concat([stored, lists_frame(SZ50, {"2025-01-06": ["Z"]})], ignore_index=True)
    stays = membership(stored, HS300)
    assert stay_rows(stays) == [
        ["A", "2025-01-06", None],
        ["B", "2025-01-06", "2025-06-16"],
        ["B", "2025-12-15", None],
        ["C", "2025-01-06", "2025-12-15"],
        ["D", "2025-06-16", None],
    ]
    assert stays["known_at"].equals(stays["effective_from"]) and stays["source"].eq(f"index:{HS300}").all()
    assert membership(stored, ZZ500).empty and membership(pd.DataFrame(), HS300).empty
    lists = stored_lists(stored, HS300)
    assert members_on(lists, date(2025, 6, 15)) == {"A", "B", "C"} and members_on(lists, date(2025, 6, 16)) == {"A", "C", "D"}
    assert members_on(lists, date(2025, 1, 5)) is None


def test_a_historical_universe_built_from_it_never_uses_a_later_list():
    stays = membership(lists_frame(HS300, {"2025-01-06": ["A", "B"], "2025-06-16": ["A", "C"]}), HS300)
    master = pd.DataFrame({"symbol": ["A", "B", "C"], "list_date": pd.Timestamp("2010-01-04"), "delist_date": pd.NaT})
    universe = HistoricalUniverse(SimpleNamespace(symbols=()), stays, master)
    assert universe.symbols == ("A", "B", "C")
    assert universe.period_symbols(date(2025, 2, 1), date(2025, 3, 1)) == ("A", "B")       # C 还没进
    assert universe.period_symbols(date(2025, 6, 16), date(2025, 9, 1)) == ("A", "C")      # B 已经出去
    assert universe.period_symbols(date(2025, 6, 1), date(2025, 7, 1)) == ("A", "B", "C")
    assert universe.period_symbols(date(2024, 6, 1), date(2024, 7, 1)) == ()               # 最早的名单之前：不知道


def test_members_whose_bars_start_late_are_reported_not_hidden():
    stays = membership(lists_frame(HS300, {"2025-01-06": ["A", "B"], "2025-06-16": ["A", "C", "D"]}), HS300)
    master = pd.DataFrame({"symbol": ["A", "B", "C", "D"], "list_date": pd.Timestamp("2010-01-04"), "delist_date": pd.NaT})
    universe = HistoricalUniverse(SimpleNamespace(symbols=()), stays, master)
    bars = pd.DataFrame({"symbol": ["A", "B", "C", "D"],
                         "trade_date": pd.to_datetime(["2024-06-03", "2025-03-03", "2025-06-18", "2025-09-01"])})
    # B 进指数两个月后才有行情；D 进指数两个多月后才有；C 只晚两天（停牌或节假日）不算。
    assert universe.members_missing_bars(bars, date(2025, 1, 6), date(2025, 12, 31)) == ["B", "D"]
    # 回测从 3 月开始：B 那时已经有行情了。7 月以后 B 已经不在指数里，只剩 D。
    assert universe.members_missing_bars(bars, date(2025, 3, 3), date(2025, 12, 31)) == ["D"]
    assert universe.members_missing_bars(bars, date(2025, 9, 1), date(2025, 12, 31)) == []

    nav = pd.DataFrame({"trade_date": pd.bdate_range("2025-01-06", periods=5), "nav": 1.0})
    report = assess_backtest_validity(nav, start_date=date(2025, 1, 6), end_date=date(2025, 1, 10),
                                      fixed_universe=False, members_missing_bars=["B", "D"])
    issue = next(issue for issue in report.issues if issue.code == "MEMBERS_MISSING_BARS")
    assert issue.severity.value == "WARNING" and "有 2 只成分股" in issue.message and "B、D" in issue.message
    assert "FIXED_UNIVERSE" not in [issue.code for issue in report.issues]     # 用的是当时的名单，没有事后选股


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #

START, TODAY = date(2023, 1, 4), date(2025, 8, 20)
# 沪深300 在这几个周一换过名单；上证50 没有变过。
CHANGES = {monday("2023-06-12"): "D", monday("2024-12-16"): "E", monday("2025-06-16"): "F"}


class Vendor:
    def __init__(self, failing=()):
        self.requests, self.failing, self.logins = [], set(failing), 0

    def login(self):
        self.logins += 1

    def close(self):
        pass

    def get_index_constituents(self, kind, day=None):
        self.requests.append((kind, day))
        if kind in self.failing or (kind, day) in self.failing:
            raise DataUnavailableError("no answer")
        if kind == "zz500" and day < date(2024, 1, 1):
            return pd.DataFrame(columns=["updateDate", "code", "code_name"])
        members = ["sh.600000", "sz.000001"] + [f"sh.60000{ord(extra) - 64}" for when, extra in CHANGES.items() if kind == "hs300" and when <= day]
        return pd.DataFrame({"updateDate": week_start(day).isoformat(), "code": members, "code_name": members})


def run(repo, vendor, start=START, today=TODAY, **options):
    return BaoStockIndexConstituentsBackfill(repo, vendor, today=today).backfill(start, date(2030, 1, 1), **options)


def test_only_the_weeks_in_which_a_list_changed_are_found_and_stored(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    vendor, seen = Vendor(), []
    result = run(repo, vendor, indexes=[HS300, SZ50], progress=lambda stage, done, total: seen.append((stage, done, total)))
    weeks = (week_start(TODAY) - week_start(START)).days // 7
    assert result["failed"] == {} and vendor.logins == 1 and result["requests"] == len(vendor.requests)
    assert seen[0] == ("index_constituents", 0, 12) and seen[-1] == ("index_constituents", 12, 12)
    assert all(day.weekday() == 0 for _, day in vendor.requests)
    lists = stored_lists(repo.read_table(CONSTITUENTS_TABLE), HS300)
    assert sorted(lists) == [week_start(START), *CHANGES]                    # 第一天，加上三次变化
    assert lists[monday("2024-12-16")] == {"600000.SH", "000001.SZ", "600004.SH", "600005.SH"}
    assert result["changes"] == 5 and len(vendor.requests) < weeks // 3      # 远少于每周问一次
    # 上证50 没有变过：只存第一天的名单，每半年只问两头。
    assert sorted(stored_lists(repo.read_table(CONSTITUENTS_TABLE), SZ50)) == [week_start(START)]
    assert [kind for kind, _ in vendor.requests].count("sz50") == 7
    checks = repo.read_table(CHECKS_TABLE)
    assert checked_range(checks, HS300) == checked_range(checks, SZ50) == (week_start(START), week_start(TODAY))
    assert checked_range(checks, ZZ500) is None

    # 再运行：没有新的一周，不请求。过了几周：只问新的那一头。
    again = Vendor()
    assert run(repo, again, indexes=[HS300, SZ50]) == {"requests": 0, "changes": 0, "failed": {}} and again.logins == 0
    later = Vendor()
    run(repo, later, today=date(2025, 9, 10), indexes=[HS300])
    assert later.requests == [("hs300", monday("2025-09-08"))]
    assert checked_range(repo.read_table(CHECKS_TABLE), HS300)[1] == monday("2025-09-08")


def test_an_earlier_start_extends_the_history_backwards(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    run(repo, Vendor(), start=date(2025, 1, 1), indexes=[HS300])
    assert sorted(stored_lists(repo.read_table(CONSTITUENTS_TABLE), HS300)) == [monday("2024-12-30"), monday("2025-06-16")]
    earlier = Vendor()
    run(repo, earlier, indexes=[HS300])
    assert all(day <= monday("2024-12-30") for _, day in earlier.requests)   # 已经核对过的日期不再问
    stays = membership(repo.read_table(CONSTITUENTS_TABLE), HS300)
    assert stay_rows(stays[stays["symbol"] != "600000.SH"]) == [
        ["000001.SZ", "2023-01-02", None], ["600004.SH", "2023-06-12", None], ["600005.SH", "2024-12-16", None],
        ["600006.SH", "2025-06-16", None]]
    assert checked_range(repo.read_table(CHECKS_TABLE), HS300) == (week_start(START), week_start(TODAY))


def test_a_failure_stops_that_index_only_and_the_next_run_continues(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    broken = ("hs300", week_start(START) + timedelta(weeks=78))             # 第三段的终点
    result = run(repo, Vendor(failing={broken, "zz500"}))
    assert sorted(key.split()[0] for key in result["failed"]) == [HS300, ZZ500]
    checks = repo.read_table(CHECKS_TABLE)
    assert checked_range(checks, HS300) == (week_start(START), week_start(START) + timedelta(weeks=52))
    assert checked_range(checks, SZ50)[1] == week_start(TODAY) and checked_range(checks, ZZ500) is None
    retry = Vendor()
    assert run(repo, retry, indexes=[HS300])["failed"] == {}
    assert min(day for _, day in retry.requests) > week_start(START) + timedelta(weeks=52)   # 从断的地方继续
    assert sorted(stored_lists(repo.read_table(CONSTITUENTS_TABLE), HS300)) == [week_start(START), *CHANGES]
    # 指数还没有的年份：厂商给的是空名单，按失败报告，不保存空名单。
    empty = run(repo, Vendor(), indexes=[ZZ500])
    assert "没有成分股数据" in next(iter(empty["failed"].values())) and checked_range(repo.read_table(CHECKS_TABLE), ZZ500) is None
    with pytest.raises(ValueError, match="不支持的指数"):
        run(repo, Vendor(), indexes=["399001.SZ"])


def test_status_and_the_background_job(tmp_path, monkeypatch):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    service = SimpleNamespace(repository=repo)
    assert DataCenterService.index_constituents_status(service)[0] == {
        "symbol": HS300, "name": "沪深300", "start_date": None, "end_date": None, "changes": 0, "members": 0}
    run(repo, Vendor(), indexes=[HS300])
    status = DataCenterService.index_constituents_status(service)
    assert [row["name"] for row in status] == ["沪深300", "上证50", "中证500"]
    assert status[0] == {"symbol": HS300, "name": "沪深300", "start_date": "2023-01-02", "end_date": "2025-08-18", "changes": 3, "members": 5}
    assert status[1]["start_date"] is None

    calls = []
    job_service = SimpleNamespace(app={"app": {"runtime_dir": str(tmp_path)}},
                                  backfill_index_constituents=lambda start, end, progress=None: calls.append((start, end)) or {"failed": {}})
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: job_service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2015-01-05", "end_date": "2025-08-20", "datasets": ["index_constituents"]}
    assert data_jobs.attempt(folder, job) == 0 and calls == [(date(2015, 1, 5), date(2025, 8, 20))]


# --------------------------------------------------------------------------- #
# Backtests on an index
# --------------------------------------------------------------------------- #

def test_a_backtest_is_refused_when_the_lists_do_not_cover_its_dates(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    with pytest.raises(ValueError, match="平台还没有沪深300的历史成分股，管理员更新后就能用"):
        require_coverage(repo.read_table(CHECKS_TABLE), HS300, date(2024, 1, 2), date(2025, 6, 30))
    run(repo, Vendor(), indexes=[HS300])
    checks = repo.read_table(CHECKS_TABLE)
    require_coverage(checks, HS300, date(2023, 1, 2), date(2025, 9, 18))     # 核对日期之后一个月以内仍然可用
    with pytest.raises(ValueError, match="从 2023-01-02 开始.*开始日期改到 2023-01-02"):
        require_coverage(checks, HS300, date(2022, 12, 30), date(2025, 6, 30))
    with pytest.raises(ValueError, match="只核对到 2025-08-18.*更新指数成分股"):
        require_coverage(checks, HS300, date(2024, 1, 2), date(2025, 9, 19))
    with pytest.raises(ValueError, match="还没有上证50"):
        require_coverage(checks, SZ50, date(2024, 1, 2), date(2025, 6, 30))


def index_service(tmp_path, monkeypatch):
    monkeypatch.chdir(BACKEND)
    service = BacktestService("configs/app.yaml")
    repo = ParquetMarketDataRepository(tmp_path / "market")
    service.configs["app"]["data"]["repository"] = str(tmp_path / "market")
    service.configs["app"]["app"]["runtime_dir"] = str(tmp_path / "runtime")
    return service, repo


def test_the_engine_gets_the_index_as_it_was_and_the_run_remembers_which_index(tmp_path, monkeypatch):
    service, repo = index_service(tmp_path, monkeypatch)
    monkeypatch.setattr(markets, "market_repository", lambda: repo)
    assert [(option["value"], option["available"]) for option in markets.market_options()] == [
        ("当前股票池", True), (HS300, False), (SZ50, False), (ZZ500, False)]
    run(repo, Vendor(), indexes=[HS300])
    options = markets.market_options()
    assert options[1] == {"value": HS300, "label": "沪深300历史成分股", "available": True, "start_date": "2023-01-02", "end_date": "2025-08-18"}
    repo.save_table("security_master", pd.DataFrame({
        "symbol": ["600000.SH", "000001.SZ", "600004.SH", "600005.SH", "600006.SH"],
        "list_date": pd.Timestamp("2010-01-04"), "delist_date": pd.NaT}))

    markets.use_market(service, "当前股票池")
    assert service.configs["universe"]["universe"].get("mode", "fixed") == "fixed"
    with pytest.raises(ValueError, match="不支持这个股票范围"):
        markets.use_market(service, "399001.SZ")
    markets.use_market(service, HS300)
    request = service.default_request()
    request = request.__class__(**{**request.__dict__, "start_date": date(2024, 1, 2), "end_date": date(2025, 6, 30)})
    engine, snapshot = service.build_engine(request)
    assert isinstance(engine.universe, HistoricalUniverse) and engine.fixed_universe is False
    assert engine.universe.period_symbols(date(2024, 1, 2), date(2024, 6, 28)) == ("000001.SZ", "600000.SH", "600004.SH")
    assert "600006.SH" in engine.universe.period_symbols(date(2025, 6, 16), date(2025, 6, 30))
    # 运行快照记下指数：参数验证用同一个范围重跑。
    assert snapshot["universe"]["universe"]["mode"] == "historical" and snapshot["universe"]["universe"]["index"] == HS300
    early = request.__class__(**{**request.__dict__, "start_date": date(2022, 6, 1)})
    with pytest.raises(ValueError, match="沪深300的历史成分股从 2023-01-02 开始"):
        service.build_engine(early)


def test_the_submit_route_refuses_an_unknown_stock_range(monkeypatch):
    app = FastAPI()
    app.include_router(backtests.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    body = {"strategy": "x", "market": "纳斯达克100", "from_date": "2024-01-02", "to_date": "2024-06-28"}
    response = TestClient(app).post("/api/v1/backtests", json=body)
    assert response.status_code == 422 and "不支持这个股票范围" in response.json()["detail"]
