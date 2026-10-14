"""Factor changes with no corporate-action record: finding them, filling them from BaoStock, and what a backtest does."""
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_platform.application import data_jobs
from quant_platform.application.data_service import DataCenterService
from quant_platform.backtest.validity import assess_backtest_validity
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.corporate_action_gaps import (
    CHECKS_TABLE,
    BaoStockDividendBackfill,
    factor_changes,
    normalize_baostock_dividends,
    unexplained_changes,
)
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

DAYS = pd.bdate_range("2024-06-03", periods=60)


def bars(symbol, factors):
    return pd.DataFrame({"symbol": symbol, "trade_date": DAYS[:len(factors)], "adj_factor": factors, "raw_close": 10.0})


def market(tmp_path):
    # A：第 10 天派息（有记录）、第 30 天配股（没有记录）。B：第 20 天停牌，第 21 天复牌时因子变了，除权日在停牌那天（有记录）。
    # C：已经退市，第 40 天分红（日常的数据源没有记录）。
    a = [1.0] * 10 + [1.02] * 20 + [1.08] * 30
    b = [1.0] * 19 + [1.05] * 41
    c = [1.0] * 40 + [1.03] * 20
    frames = [bars("000001.SZ", a), bars("000002.SZ", b).drop(index=19), bars("000003.SZ", c)]
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", pd.concat(frames, ignore_index=True))
    repo.save_table("corporate_actions", pd.DataFrame([
        {"symbol": "000001.SZ", "ex_date": DAYS[10], "cash_per_share": 0.2, "share_multiplier": 1.0},
        {"symbol": "000002.SZ", "ex_date": DAYS[19], "cash_per_share": 0.5, "share_multiplier": 1.0},
    ]))
    return repo


def test_changes_without_a_record_between_the_previous_bar_and_the_change_are_found(tmp_path):
    repo = market(tmp_path)
    changes = repo.adj_factor_changes()
    assert sorted(zip(changes["symbol"], changes["trade_date"])) == [
        ("000001.SZ", DAYS[10]), ("000001.SZ", DAYS[30]), ("000002.SZ", DAYS[20]), ("000003.SZ", DAYS[40])]
    gaps = unexplained_changes(changes, repo.read_table("corporate_actions"))
    assert sorted(zip(gaps["symbol"], gaps["trade_date"])) == [("000001.SZ", DAYS[30]), ("000003.SZ", DAYS[40])]
    assert gaps.set_index("symbol").loc["000001.SZ", "ratio"] == pytest.approx(1.08 / 1.02)
    assert len(unexplained_changes(changes, pd.DataFrame())) == 4
    # 因子在容差以内的抖动不算变化；缺失或为 0 的因子不参与比较。
    noisy = pd.DataFrame({"symbol": "X", "trade_date": DAYS[:4], "adj_factor": [1.0, 1.0 + 1e-9, None, 0.0]})
    assert factor_changes(noisy).empty and factor_changes(pd.DataFrame()).empty


def test_baostock_dividends_become_per_share_records():
    vendor = pd.DataFrame({
        "code": "sz.000003", "dividOperateDate": ["2016-06-07", "2016-06-07", "2017-07-14", "", "2018-07-12"],
        "dividCashPsBeforeTax": ["0.1", "0.05", "0.06", "0.3", "0"], "dividCashPsAfterTax": ["", "", "", "", ""],
        "dividStocksPs": ["0.3", "", "0", "", "0"], "dividReserveToStockPs": ["0.5", "", "0", "", "0"],
    })
    rows = normalize_baostock_dividends(vendor, "000003.SZ")
    assert rows[["symbol", "ex_date", "cash_per_share", "share_multiplier"]].values.tolist() == [
        ["000003.SZ", pd.Timestamp("2016-06-07"), pytest.approx(0.15), pytest.approx(1.8)],   # 同一天的两次合并
        ["000003.SZ", pd.Timestamp("2017-07-14"), pytest.approx(0.06), 1.0],
    ]                                                                                          # 没有日期、什么都没派的不要
    assert rows["source"].eq("baostock").all()
    assert normalize_baostock_dividends(pd.DataFrame(), "000003.SZ").empty


class Vendor:
    def __init__(self, failing=()):
        self.requests, self.failing, self.logins = [], set(failing), 0

    def login(self):
        self.logins += 1

    def close(self):
        pass

    def get_dividends(self, symbol, year):
        self.requests.append((symbol, year))
        if symbol in self.failing:
            raise DataUnavailableError("no answer")
        rows = {"000003.SZ": [(DAYS[40], "0.3"), (DAYS[5], "0.1")]}.get(symbol, [])  # 第 5 天那条和缺口无关
        return pd.DataFrame({"dividOperateDate": [day.date().isoformat() for day, _ in rows],
                             "dividCashPsBeforeTax": [cash for _, cash in rows], "dividStocksPs": "0", "dividReserveToStockPs": "0"})


def test_only_the_records_that_explain_a_gap_are_added_and_past_years_are_not_asked_twice(tmp_path):
    repo = market(tmp_path)
    vendor, seen = Vendor(), []
    result = BaoStockDividendBackfill(repo, vendor).backfill(progress=lambda stage, done, total: seen.append((stage, done, total)))
    assert vendor.requests == [("000001.SZ", 2024), ("000003.SZ", 2024)] and vendor.logins == 1
    assert result == {"requests": 2, "added": 1, "failed": {}, "unexplained_before": 2, "unexplained_after": 1}
    assert seen[-1] == ("corporate_action_gaps", 2, 2)
    actions = repo.read_table("corporate_actions")
    added = actions[actions["symbol"] == "000003.SZ"]
    assert added[["ex_date", "cash_per_share"]].values.tolist() == [[DAYS[40], 0.3]]
    assert len(actions) == 3                                                   # 已有的记录没有变
    assert len(repo.read_table(CHECKS_TABLE)) == 2

    # 往年查过就不再查；今年的还会再查（新的记录可能还没出来）。
    assert BaoStockDividendBackfill(repo, Vendor()).plan(today=date(2026, 1, 5)) == {}
    assert BaoStockDividendBackfill(repo, Vendor()).plan(today=date(2024, 12, 1)) == {"000001.SZ": [2024]}


def test_a_failed_stock_is_reported_and_asked_again(tmp_path):
    repo = market(tmp_path)
    result = BaoStockDividendBackfill(repo, Vendor(failing={"000003.SZ"})).backfill()
    assert list(result["failed"]) == ["000003.SZ"] and result["unexplained_after"] == 2
    assert BaoStockDividendBackfill(repo, Vendor()).plan(today=date(2026, 1, 5)) == {"000003.SZ": [2024]}


def test_status_and_the_background_job(tmp_path, monkeypatch):
    repo = market(tmp_path)
    service = SimpleNamespace(repository=repo)
    assert DataCenterService.corporate_action_gap_status(service) == {"changes": 2, "symbols": 2, "to_check": 2}
    BaoStockDividendBackfill(repo, Vendor()).backfill()
    status = DataCenterService.corporate_action_gap_status(service)
    assert status["changes"] == 1 and status["symbols"] == 1

    calls = []
    job_service = SimpleNamespace(app={"app": {"runtime_dir": str(tmp_path)}},
                                  backfill_corporate_action_gaps=lambda progress=None: calls.append("run") or {"failed": {}})
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: job_service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2015-01-05", "end_date": "2026-10-14", "datasets": ["action_gaps"]}
    assert data_jobs.attempt(folder, job) == 0 and calls == ["run"]


def test_a_backtest_reports_each_settlement_it_had_to_infer():
    nav = pd.DataFrame({"trade_date": pd.bdate_range("2022-01-24", periods=5), "nav": 1.0})
    implied = [{"symbol": "600030.SH", "ex_date": date(2022, 1, 27), "ratio": 1.0607, "cash_per_share": 1.47}]
    report = assess_backtest_validity(nav, start_date=date(2022, 1, 24), end_date=date(2022, 1, 28), implied_actions=implied)
    issue = next(issue for issue in report.issues if issue.code == "IMPLIED_CORPORATE_ACTIONS")
    assert issue.severity.value == "WARNING" and "600030.SH 2022-01-27" in issue.message and "多半是配股" in issue.message
    many = implied * 7
    assert "等 7 次" in next(i for i in assess_backtest_validity(nav, start_date=date(2022, 1, 24), end_date=date(2022, 1, 28),
                                                             implied_actions=many).issues if i.code == "IMPLIED_CORPORATE_ACTIONS").message
