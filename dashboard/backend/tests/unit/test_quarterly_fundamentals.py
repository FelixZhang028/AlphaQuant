"""Quarterly financial reports: downloaded per period, used only from their publication day."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.application import data_jobs
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.extras import extra_columns
from quant_platform.data.fundamentals import (
    FUNDAMENTAL_COLUMNS,
    FUNDAMENTALS_TABLE,
    MISSING_FUNDAMENTALS_MESSAGE,
    STORED_COLUMNS,
    checked_empty_row,
    normalize_baostock_quarter,
    point_in_time,
    quarter_end,
    quarters_between,
)
from quant_platform.data.fundamentals_backfill import BaoStockFundamentalsBackfill
from quant_platform.data.indicators import INDICATOR_TABLE, MISSING_INDICATORS_MESSAGE
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.factors.registry import default_registry

TODAY = date(2025, 7, 15)          # 2025 年半年报（7 月 25 日公告）这一天还没有出来


def section(pub, **values):
    return pd.DataFrame([{"code": "sz.000001", "pubDate": pub, "statDate": "x", **{key: str(value) for key, value in values.items()}}])


def report(symbol, stat, pub, **values):
    row = {column: np.nan for column in STORED_COLUMNS}
    row.update(symbol=symbol, stat_date=pd.Timestamp(stat), pub_date=pd.Timestamp(pub) if pub else pd.NaT, source="baostock", **values)
    return row


def days_frame(symbol, days):
    return pd.DataFrame({"symbol": symbol, "trade_date": pd.to_datetime(days)})


# --------------------------------------------------------------------------- #
# Periods and normalizing
# --------------------------------------------------------------------------- #


def test_reporting_periods_are_calendar_quarter_ends():
    assert [quarter_end(2025, quarter) for quarter in (1, 2, 3, 4)] == [date(2025, 3, 31), date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31)]
    assert quarters_between(date(2024, 10, 1), date(2025, 6, 30)) == [(2024, 4), (2025, 1), (2025, 2)]
    assert quarters_between(date(2025, 7, 1), date(2025, 9, 29)) == []


def test_one_row_is_built_from_the_three_report_sections():
    row = normalize_baostock_quarter("sz.000001", 2025, 2, {
        "profit": section("2025-08-23", roeAvg=0.0495, npMargin=0.31, gpMargin="", netProfit=24870000000, epsTTM=2.2, MBRevenue="", totalShare=19405918198, liqaShare=19405600653),
        "growth": section("2025-08-23", YOYEquity=0.08, YOYAsset=0.02, YOYNI=-0.039, YOYEPSBasic=-0.04, YOYPNI=-0.039),
        "balance": section("2025-08-26", currentRatio="", quickRatio="", assetToEquity=10.9),
    })
    assert (row["symbol"], row["stat_date"], row["source"]) == ("000001.SZ", pd.Timestamp("2025-06-30"), "baostock")
    # 各部分的公告日不一样时取最晚的那天：整行数据都公开之后才使用。
    assert row["pub_date"] == pd.Timestamp("2025-08-26")
    assert (row["roe_avg"], row["yoy_net_profit"], row["asset_to_equity"], row["total_shares"]) == (0.0495, -0.039, 10.9, 19405918198.0)
    assert np.isnan(row["gross_margin"]) and np.isnan(row["revenue"]) and np.isnan(row["current_ratio"])     # 银行没有毛利率
    assert set(FUNDAMENTAL_COLUMNS) <= set(row)


def test_a_period_without_any_published_section_is_not_a_report():
    assert normalize_baostock_quarter("sz.000001", 2025, 3, {"profit": pd.DataFrame()}) is None
    only_profit = normalize_baostock_quarter("sz.000001", 2025, 1, {"profit": section("2025-04-19", roeAvg=0.028)})
    assert only_profit["roe_avg"] == 0.028 and np.isnan(only_profit["yoy_equity"])


def test_a_report_given_in_percent_instead_of_fractions_loses_the_affected_ratios():
    row = normalize_baostock_quarter("sz.300750", 2018, 1, {
        "profit": section("2018-05-22", roeAvg=1.658721, npMargin=0.12643, gpMargin=32.76181, totalShare=1955193267),
        "growth": section("2018-05-22", YOYNI=2744.854824, YOYEquity=""),
        "balance": section("2018-05-22", assetToEquity=1.772464),
    })
    # 毛利率 32.76 只能是百分数；同一份里净利率却是小数。不猜换算方式，受影响的比率置空。
    assert all(np.isnan(row[column]) for column in ("gross_margin", "roe_avg", "yoy_net_profit"))
    assert (row["net_margin"], row["asset_to_equity"], row["total_shares"]) == (0.12643, 1.772464, 1955193267.0)


# --------------------------------------------------------------------------- #
# Point in time
# --------------------------------------------------------------------------- #


def reports_frame(*rows):
    return pd.DataFrame(list(rows), columns=STORED_COLUMNS)


def test_a_report_counts_from_its_publication_day_not_from_the_period_end():
    reports = reports_frame(
        report("A", "2025-03-31", "2025-04-25", roe_avg=0.03),
        report("A", "2025-06-30", "2025-08-16", roe_avg=0.05),        # 周六公告
    )
    days = days_frame("A", ["2025-04-24", "2025-04-25", "2025-06-30", "2025-08-15", "2025-08-18"])
    values = point_in_time(days, reports, ["roe_avg"])["roe_avg"].tolist()
    assert np.isnan(values[0])                                         # 第一份财报公告之前：没有值
    assert values[1:] == [0.03, 0.03, 0.03, 0.05]                      # 6 月 30 日当天还只能用一季报


def test_two_reports_published_the_same_day_the_newer_period_wins():
    reports = reports_frame(
        report("A", "2025-03-31", "2025-04-28", roe_avg=0.03),         # 年报和一季报同一天公告
        report("A", "2024-12-31", "2025-04-28", roe_avg=0.12),
    )
    assert point_in_time(days_frame("A", ["2025-04-28", "2025-05-06"]), reports, ["roe_avg"])["roe_avg"].tolist() == [0.03, 0.03]


def test_an_older_period_published_late_does_not_replace_a_newer_one():
    reports = reports_frame(
        report("A", "2025-06-30", "2025-08-20", roe_avg=0.05),
        report("A", "2025-03-31", "2025-09-10", roe_avg=0.99),         # 迟到的更正
    )
    assert point_in_time(days_frame("A", ["2025-08-21", "2025-09-11"]), reports, ["roe_avg"])["roe_avg"].tolist() == [0.05, 0.05]


def test_stale_reports_markers_and_other_stocks_are_not_used():
    reports = reports_frame(
        report("A", "2023-12-31", "2024-03-20", roe_avg=0.10),
        checked_empty_row("sz.000002", 2024, 1),
        report("B", "2025-03-31", "2025-04-25", roe_avg=0.20),
    )
    days = pd.concat([days_frame("A", ["2024-06-03", "2025-03-25", "2025-03-27"]), days_frame("000002.SZ", ["2025-01-02"]), days_frame("B", ["2025-04-24", "2025-04-25"])])
    values = point_in_time(days, reports, ["roe_avg"])
    # A 的财报 2024-03-20 公告，370 天后（2025-03-25）仍可用，再往后就太旧了。
    assert values["roe_avg"].tolist()[:2] == [0.10, 0.10] and np.isnan(values["roe_avg"].tolist()[2])
    assert np.isnan(values["roe_avg"].tolist()[3]) and np.isnan(values["roe_avg"].tolist()[4]) and values["roe_avg"].tolist()[5] == 0.20
    assert values[["symbol", "trade_date"]].reset_index(drop=True).equals(days.assign(trade_date=days["trade_date"].astype("datetime64[ns]")).reset_index(drop=True))
    assert point_in_time(days, reports_frame(), ["roe_avg"])["roe_avg"].isna().all()


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #

DAYS = pd.bdate_range("2024-06-03", "2025-08-29")


def bars(symbol, days):
    return pd.DataFrame({"symbol": symbol, "trade_date": days, "raw_open": 10.0, "raw_high": 10.5, "raw_low": 9.8, "raw_close": 10.0,
                         "pre_close": 10.0, "volume": 1000.0, "amount": 10000.0, "adjusted_close": 10.0, "adj_factor": 1.0,
                         "quality_status": "OK", "source": "baostock"})


class Vendor:
    """Publishes a report 25 days after each quarter end, for quarters from ``first`` on."""

    def __init__(self, first=(2023, 4), failing=()):
        self.first, self.failing, self.requests, self.logins = first, set(failing), [], 0

    def login(self):
        self.logins += 1

    def close(self):
        pass

    def get_quarterly_report(self, kind, symbol, year, quarter):
        self.requests.append((kind, symbol, year, quarter))
        if symbol in self.failing:
            raise DataUnavailableError("no answer")
        published = pd.Timestamp(quarter_end(year, quarter)) + pd.Timedelta(days=25)
        if (year, quarter) < self.first or published.date() > TODAY:
            return pd.DataFrame()
        values = {"profit": {"roeAvg": 0.02 * quarter, "gpMargin": 0.3, "totalShare": 1e9}, "growth": {"YOYNI": 0.1, "YOYEquity": 0.05},
                  "balance": {"assetToEquity": 2.0}}[kind]
        return section(published.date().isoformat(), **values)


@pytest.fixture
def repo(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("daily_bars", pd.concat([bars("000001.SZ", DAYS), bars("600519.SH", DAYS[100:])], ignore_index=True))
    return repository


def run(repo, vendor, **options):
    return BaoStockFundamentalsBackfill(repo, vendor, today=TODAY).backfill(date(2015, 1, 1), date(2030, 1, 1), **options)


def test_download_covers_each_stocks_periods_and_keeps_what_the_vendor_does_not_have(repo):
    vendor, seen = Vendor(), []
    result = run(repo, vendor, progress=lambda stage, done, total: seen.append((stage, done, total)))
    # 000001 的行情从 2024-06 开始：从前一年（2023Q2）取到今天所在的季度之前。
    asked = sorted({(year, quarter) for kind, symbol, year, quarter in vendor.requests if symbol == "000001.SZ"})
    assert asked == [(2023, 2), (2023, 3), (2023, 4), (2024, 1), (2024, 2), (2024, 3), (2024, 4), (2025, 1), (2025, 2)]
    assert result == {"symbols": 2, "updated": 2, "reports": 12, "failed": {}}
    assert vendor.logins == 1 and seen[0] == ("quarterly_fundamentals", 0, 2) and seen[-1] == ("quarterly_fundamentals", 2, 2)
    # 没有利润表的季度不再去问另外两张表。
    assert [kind for kind, symbol, year, quarter in vendor.requests if (symbol, year, quarter) == ("000001.SZ", 2023, 2)] == ["profit"]
    assert [kind for kind, symbol, year, quarter in vendor.requests if (symbol, year, quarter) == ("000001.SZ", 2024, 1)] == ["profit", "growth", "balance"]

    stored = repo.get_fundamentals(["000001.SZ"])
    markers = stored[stored["pub_date"].isna()]["stat_date"].dt.date.tolist()
    # 一年多以前还没有财报的季度记成“问过了、没有”；最近的（2025Q2 还没公告）不记，下次再问。
    assert markers == [date(2023, 6, 30), date(2023, 9, 30)] and len(stored) == 8
    assert stored["roe_avg"].dropna().tolist() == [0.08, 0.02, 0.04, 0.06, 0.08, 0.02]


def test_a_second_run_only_asks_for_periods_that_may_have_been_published_since(repo):
    run(repo, Vendor())
    again = Vendor()
    result = run(repo, again)
    assert sorted({(symbol, year, quarter) for kind, symbol, year, quarter in again.requests}) == [("000001.SZ", 2025, 2), ("600519.SH", 2025, 2)]
    assert result["reports"] == 0
    only = Vendor()
    BaoStockFundamentalsBackfill(repo, only, today=date(2025, 12, 1)).backfill(date(2015, 1, 1), date(2030, 1, 1), symbols=["600519.SH"])
    assert {symbol for kind, symbol, year, quarter in only.requests} == {"600519.SH"}


def test_failures_are_tolerated_until_the_source_is_clearly_down(repo, tmp_path, monkeypatch):
    result = run(repo, Vendor(failing={"000001.SZ"}))
    assert result["updated"] == 1 and list(result["failed"]) == ["000001.SZ"]
    assert set(repo.get_fundamentals()["symbol"]) == {"600519.SH"}

    many = ParquetMarketDataRepository(tmp_path / "many")
    symbols = [f"{number:06d}.SZ" for number in range(1, 9)]
    many.save_table("daily_bars", pd.concat([bars(symbol, DAYS[-30:]) for symbol in symbols], ignore_index=True))
    monkeypatch.setattr("quant_platform.data.fundamentals_backfill.CONSECUTIVE_FAILURE_LIMIT", 3)
    with pytest.raises(DataUnavailableError, match="连续 3 只股票取不到财务数据.*稍后重新运行即可继续"):
        run(many, Vendor(failing=set(symbols[1:])))
    assert set(many.get_fundamentals()["symbol"]) == {symbols[0]}
    assert run(ParquetMarketDataRepository(tmp_path / "empty"), Vendor()) == {"symbols": 0, "updated": 0, "reports": 0, "failed": {}}


# --------------------------------------------------------------------------- #
# Reading with bars, factors
# --------------------------------------------------------------------------- #


def test_bars_can_carry_report_columns_matched_by_publication_day(repo):
    run(repo, Vendor())
    loaded = repo.get_daily_bars(["000001.SZ"], date(2025, 4, 22), date(2025, 4, 30), extras=["roe_avg", "total_shares", "raw_close"])
    assert list(loaded.columns[-2:]) == ["roe_avg", "total_shares"] and len(loaded) == 7
    # 2025Q1 的财报 4 月 25 日公告：之前用的是 2024 年报。
    assert loaded.set_index("trade_date")["roe_avg"].round(2).tolist() == [0.08, 0.08, 0.08, 0.02, 0.02, 0.02, 0.02]
    assert extra_columns(["raw_close", "total_shares", "pe_ttm", "gross_margin"]) == ["pe_ttm", "gross_margin", "total_shares"]
    assert list(repo.get_daily_bars(["000001.SZ"], date(2025, 4, 22), date(2025, 4, 22)).columns) == list(bars("000001.SZ", DAYS[:1]).columns)


def factor(name):
    return default_registry().get(name)


def test_quality_growth_and_size_factors(repo):
    run(repo, Vendor())
    repo.save_table(INDICATOR_TABLE, pd.DataFrame({"symbol": "000001.SZ", "trade_date": DAYS[-5:], "pe_ttm": 10.0, "pb_mrq": 1.5,
                                                   "ps_ttm": 2.0, "pcf_ttm": 8.0, "turnover_rate": 1.0, "source": "baostock"}))
    fields = ["pe_ttm", "pb_mrq", "ps_ttm", "gross_margin", "asset_to_equity", "yoy_net_profit", "yoy_equity", "total_shares"]
    loaded = repo.get_daily_bars(["000001.SZ"], DAYS[-5].date(), DAYS[-1].date(), extras=fields)
    value = lambda name: factor(name).compute(loaded)["value"].iloc[-1]  # noqa: E731
    assert value("roe_ttm") == pytest.approx(1.5 / 10.0) and value("net_margin_ttm") == pytest.approx(2.0 / 10.0)
    assert value("gross_margin") == pytest.approx(0.3) and value("yoy_net_profit") == pytest.approx(0.1) and value("yoy_equity") == pytest.approx(0.05)
    assert value("debt_ratio") == pytest.approx(0.5)                               # 权益乘数 2：一半是负债
    assert value("ln_market_cap") == pytest.approx(np.log(10.0 * 1e9))
    assert (factor("debt_ratio").direction, factor("ln_market_cap").direction, factor("roe_ttm").direction) == (-1, -1, 1)
    assert {factor(name).category for name in ("roe_ttm", "net_margin_ttm", "gross_margin", "debt_ratio")} == {"质量"}
    assert {factor(name).category for name in ("yoy_net_profit", "yoy_equity")} == {"成长"} and factor("ln_market_cap").category == "规模"


def test_factors_say_which_data_is_missing(repo):
    with pytest.raises(ValueError) as error:
        FactorEvaluator(repo).evaluate(factor("gross_margin"), DAYS[-30].date(), DAYS[-1].date(), horizon=1, n_groups=2)
    assert str(error.value) == MISSING_FUNDAMENTALS_MESSAGE
    with pytest.raises(ValueError) as error:
        FactorEvaluator(repo).evaluate(factor("roe_ttm"), DAYS[-30].date(), DAYS[-1].date(), horizon=1, n_groups=2)
    assert str(error.value) == MISSING_INDICATORS_MESSAGE
    run(repo, Vendor())
    report_ = FactorEvaluator(repo).evaluate(factor("gross_margin"), DAYS[-30].date(), DAYS[-2].date(), horizon=1, n_groups=2)
    assert report_ is not None


# --------------------------------------------------------------------------- #
# Background job and route
# --------------------------------------------------------------------------- #


def test_the_job_passes_the_chosen_stocks_to_the_download(tmp_path, monkeypatch):
    calls = []
    service = SimpleNamespace(
        app={"app": {"runtime_dir": str(tmp_path)}},
        run_closed_loop=lambda *args, **options: calls.append("closed_loop") or {},
        backfill_daily_indicators=lambda *args, **options: calls.append("indicators") or {"failed": {}},
        backfill_fundamentals=lambda start, end, symbols=None, progress=None: calls.append(("fundamentals", symbols)) or {"failed": {}, "reports": 5},
    )
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2024-01-02", "end_date": "2024-06-28", "datasets": ["fundamentals"], "symbols": ["000001.SZ"]}
    assert data_jobs.attempt(folder, job) == 0 and calls == [("fundamentals", ["000001.SZ"])]
    assert data_jobs.read_json(folder / "result.json") == {"quarterly_fundamentals": {"failed": {}, "reports": 5}}
    calls.clear()
    assert data_jobs.attempt(folder, {**job, "symbols": None, "datasets": ["indicators", "fundamentals"]}) == 0
    assert calls == ["indicators", ("fundamentals", None)]


def test_starting_a_pool_download_sends_the_users_stock_pool(monkeypatch):
    started = []
    jobs = SimpleNamespace(start=lambda start, end, datasets, symbols=None: started.append((start, end, datasets, symbols)) or {"id": "j", "status": "STARTING"})
    monkeypatch.setattr(workspace, "_data_jobs", lambda: jobs)
    pool = ["000001", "600519"]
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda user_id: pool)
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 7}
    client = TestClient(app)
    body = {"start_date": "2015-01-05", "end_date": "2025-08-29", "datasets": ["fundamentals"], "scope": "universe"}
    assert client.post("/api/v1/data-center/jobs/start", json=body).status_code == 201
    assert started[-1] == (date(2015, 1, 5), date(2025, 8, 29), ["fundamentals"], ["000001.SZ", "600519.SH"])
    assert client.post("/api/v1/data-center/jobs/start", json={**body, "scope": None}).status_code == 201 and started[-1][3] is None
    pool.clear()
    assert client.post("/api/v1/data-center/jobs/start", json=body).status_code == 409


def test_status_counts_stocks_with_at_least_one_published_report(repo):
    from quant_platform.application.data_service import DataCenterService

    service = SimpleNamespace(repository=repo)
    assert DataCenterService.fundamentals_status(service) == {"symbols": 0, "missing_symbols": 2, "reports": 0, "latest_stat_date": None, "latest_pub_date": None}
    run(repo, Vendor(), symbols=["000001.SZ"])
    assert DataCenterService.fundamentals_status(service) == {
        "symbols": 1, "missing_symbols": 1, "reports": 6, "latest_stat_date": "2025-03-31", "latest_pub_date": "2025-04-25"}
    assert repo.get_fundamentals()[FUNDAMENTALS_TABLE and "symbol"].nunique() == 1
