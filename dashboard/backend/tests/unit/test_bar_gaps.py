"""Stocks whose local bars start later than they should, and the job that downloads them again."""
from datetime import date
from types import SimpleNamespace

import pandas as pd

from quant_platform.application import data_jobs
from quant_platform.application.data_service import DataCenterService
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.bar_gaps import stocks_missing_history
from quant_platform.data.full_market_backfill import FullMarketBackfill
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository

DAYS = pd.bdate_range("2024-01-02", periods=120)
START, END = DAYS[0].date(), DAYS[-1].date()


def bars(symbol, days):
    return pd.DataFrame({"symbol": symbol, "trade_date": days, "raw_open": 10.0, "raw_high": 10.6, "raw_low": 9.8, "raw_close": 10.2,
                         "pre_close": 10.0, "volume": 100000.0, "amount": 1020000.0, "adjusted_close": 10.2, "adj_factor": 1.0,
                         "quality_status": "OK", "source": "baostock"})


MASTER = pd.DataFrame([
    {"symbol": "000001.SZ", "name": "完整", "list_date": "1991-04-03", "delist_date": None},       # 行情从第一天开始
    {"symbol": "000002.SZ", "name": "开始得晚", "list_date": "1991-01-29", "delist_date": None},   # 行情从第 60 天才开始
    {"symbol": "000003.SZ", "name": "没有行情", "list_date": "2010-07-16", "delist_date": "2024-03-29"},
    {"symbol": "000004.SZ", "name": "新股", "list_date": DAYS[40].date().isoformat(), "delist_date": None},  # 上市后 3 天才有行情
    {"symbol": "000005.SZ", "name": "早已退市", "list_date": "1995-01-04", "delist_date": "2019-05-31"},
    {"symbol": "920001.BJ", "name": "没有上市日期", "list_date": None, "delist_date": None},
])


def market(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", pd.concat([bars("000001.SZ", DAYS), bars("000002.SZ", DAYS[60:]), bars("000004.SZ", DAYS[43:])], ignore_index=True))
    repo.save_table("security_master", MASTER)
    return repo


def test_a_stock_is_missing_history_when_its_bars_start_late_or_do_not_exist(tmp_path):
    repo = market(tmp_path)
    gaps = stocks_missing_history(repo.daily_bar_summary(), MASTER, START, END)
    assert gaps["symbol"].tolist() == ["000002.SZ", "000003.SZ"]
    late, absent = gaps.iloc[0], gaps.iloc[1]
    assert (late["name"], late["expected_start"], late["first_bar"]) == ("开始得晚", DAYS[0], DAYS[60])
    assert absent["expected_start"] == DAYS[0] and pd.isna(absent["first_bar"])
    # 新股上市后几天才有行情不算；范围开始前就退市的、没有上市日期的不比较。
    assert not set(gaps["symbol"]) & {"000004.SZ", "000005.SZ", "920001.BJ"}
    assert stocks_missing_history(repo.daily_bar_summary(), pd.DataFrame(), START, END).empty
    # 本地一根行情都没有时，范围里上市的股票全部算缺。
    empty = ParquetMarketDataRepository(tmp_path / "empty")
    assert len(stocks_missing_history(empty.daily_bar_summary(), MASTER, START, END)) == 4


class Range:
    """Stands in for the vendor download of one stock's whole history."""

    def __init__(self, failing=()):
        self.requests, self.failing = [], set(failing)

    def fetch_symbol(self, symbol, start_date, end_date, master):
        self.requests.append((symbol, start_date, end_date))
        if symbol in self.failing:
            raise DataUnavailableError("no answer")
        days = DAYS[:62] if symbol == "000003.SZ" else DAYS          # 退市的那只只有到退市日的行情
        return bars(symbol, days).assign(adj_factor=2.0)


def backfill(tmp_path, repo, vendor):
    provider = SimpleNamespace(login=lambda: None, close=lambda: None)
    job = FullMarketBackfill(RawDataRepository(tmp_path / "raw"), repo, provider)
    job._range_backfill = vendor
    return job


def test_only_the_stocks_with_gaps_are_downloaded_again_in_full(tmp_path):
    repo = market(tmp_path)
    vendor, seen = Range(), []
    result = backfill(tmp_path, repo, vendor).repair_bar_gaps(START, END, progress=lambda stage, done, total: seen.append((stage, done, total)))
    assert vendor.requests == [("000002.SZ", START, END), ("000003.SZ", START, END)]
    assert result == {"total": 2, "done": 2, "failed": {}, "rows_this_run": 182, "still_missing": []}
    assert seen[0] == ("bar_gaps", 0, 2) and seen[-1] == ("bar_gaps", 2, 2)
    summary = repo.daily_bar_summary()
    assert summary.loc["000002.SZ", "start"] == DAYS[0] and summary.loc["000002.SZ", "rows"] == 120
    assert summary.loc["000003.SZ", "rows"] == 62
    stored = repo.get_daily_bars(["000001.SZ", "000002.SZ"])
    # 整只股票重新下载：同一只股票的复权因子是同一个基准；没有缺口的股票没有动。
    assert stored[stored.symbol == "000002.SZ"]["adj_factor"].eq(2.0).all()
    assert stored[stored.symbol == "000001.SZ"]["adj_factor"].eq(1.0).all()
    # 历史股票池跟着重建：补回来的股票从第一天起就在里面。
    membership = repo.read_table("universe_membership").set_index("symbol")
    assert membership.loc["000002.SZ", "effective_from"] == DAYS[0] and "000003.SZ" in membership.index

    again = Range()
    assert backfill(tmp_path, repo, again).repair_bar_gaps(START, END)["total"] == 0 and again.requests == []


def test_a_failed_stock_is_reported_and_stays_on_the_list(tmp_path):
    repo = market(tmp_path)
    result = backfill(tmp_path, repo, Range(failing={"000003.SZ"})).repair_bar_gaps(START, END)
    assert result["done"] == 1 and list(result["failed"]) == ["000003.SZ"] and result["still_missing"] == ["000003.SZ"]
    retry = Range()
    backfill(tmp_path, repo, retry).repair_bar_gaps(START, END)
    assert [symbol for symbol, _, _ in retry.requests] == ["000003.SZ"]


def test_status_and_the_background_job(tmp_path, monkeypatch):
    repo = market(tmp_path)
    service = SimpleNamespace(repository=repo)
    status = DataCenterService.bar_gap_status(service)
    assert status["symbols"] == 2 and status["without_bars"] == 1
    assert status["examples"] == [
        {"symbol": "000002.SZ", "name": "开始得晚", "expected_start": START.isoformat(), "first_bar": DAYS[60].date().isoformat()},
        {"symbol": "000003.SZ", "name": "没有行情", "expected_start": START.isoformat(), "first_bar": None},
    ]
    empty = SimpleNamespace(repository=ParquetMarketDataRepository(tmp_path / "empty"))
    assert DataCenterService.bar_gap_status(empty) == {"symbols": 0, "without_bars": 0, "examples": []}

    calls = []
    job_service = SimpleNamespace(app={"app": {"runtime_dir": str(tmp_path)}},
                                  repair_bar_gaps=lambda start, end, progress=None: calls.append((start, end)) or {"failed": {}, "total": 2})
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: job_service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2015-01-05", "end_date": "2026-10-14", "datasets": ["bar_gaps"]}
    assert data_jobs.attempt(folder, job) == 0 and calls == [(date(2015, 1, 5), date(2026, 10, 14))]
