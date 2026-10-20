"""Every trading day after the close the whole market is updated automatically; data downloads are admin-only."""
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant import daily_schedule
from app.quant.daily_schedule import CHINA, DailyScheduler, decide
from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.application import daily_update, data_jobs
from quant_platform.application.daily_update import DailyUpdate
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

TODAY = date(2026, 10, 16)            # 星期五


# --------------------------------------------------------------------------- #
# One day's update
# --------------------------------------------------------------------------- #


class Provider:
    def __init__(self, trading=True, published=True):
        self.trading, self.published, self.closed = trading, published, 0

    def get_trade_calendar(self, start, end):
        return pd.DataFrame({"calendar_date": [start.isoformat()], "is_trading_day": ["1" if self.trading else "0"]})

    def get_history_range(self, symbol, start, end, *, adjustflag):
        return pd.DataFrame({"date": [start.isoformat()], "code": [symbol]}) if self.published else pd.DataFrame()

    def close(self):
        self.closed += 1


class Service:
    """Records what the daily update asks the data service to do."""

    def __init__(self, provider=None, stored=("A.SZ", "B.SZ", "C.SZ", "D.SZ"), failing_benchmarks=(), failing_symbols=()):
        self.calls, self.fetched = [], []
        self.failing_symbols = set(failing_symbols)
        self.provider = provider or Provider()
        self.failing_benchmarks = set(failing_benchmarks)
        master = pd.DataFrame({
            "symbol": ["A.SZ", "B.SZ", "C.SZ", "D.SZ", "E.SZ", "OLD.SZ", "LATER.SZ", "830799.BJ"],
            "list_date": ["2010-01-04"] * 4 + ["2026-10-09", "2005-01-04", "2026-11-02", "2021-11-15"],
            "delist_date": [None] * 5 + ["2020-06-01", None, None],
        })
        summary = pd.DataFrame({"end": pd.Timestamp("2026-10-15")}, index=pd.Index(list(stored), name="symbol"))
        benchmarks = pd.DataFrame({"symbol": ["000300.SH", "000905.SH"], "trade_date": ["2026-10-15"] * 2})
        tables = {"security_master": master, "benchmark_bars": benchmarks}
        self.repository = SimpleNamespace(read_table=lambda name: tables.get(name, pd.DataFrame()), daily_bar_summary=lambda: summary)
        self.sources = SimpleNamespace(baostock_provider=lambda: self.provider)
        backfill = SimpleNamespace(
            refresh_security_master=lambda: self.calls.append("security_master") or master,
            build_universe_membership=lambda: self.calls.append("universe") or pd.DataFrame({"symbol": ["A.SZ"]}),
            build_delisting_settlements=lambda: self.calls.append("settlements") or pd.DataFrame(),
        )
        self.full_market_backfill = lambda: backfill

    def update_market_data(self, start, end, symbols, *, source_order=None, allow_fallback=None, on_symbol=None):
        self.calls.append("bars")
        assert (source_order, allow_fallback) == (["baostock"], False)       # 只用 BaoStock，不白白尝试备用来源
        if set(symbols) & self.failing_symbols:
            raise RuntimeError("BaoStock 没有返回")
        self.fetched.append((start, list(symbols)))
        for symbol in symbols:
            on_symbol(symbol)
        return SimpleNamespace(message="行情更新完成（来源：BaoStock）")

    def backfill_corporate_action_gaps(self, *, progress=None):
        self.calls.append("actions")
        return {"changes": 2, "added": 1, "failed": {}}

    def repair_benchmarks(self):
        self.calls.append("repair_benchmarks")
        return {"removed": 0, "detail": "", "errors": []}

    def update_benchmark(self, start, end, symbol):
        self.calls.append(f"benchmark:{symbol}")
        if symbol in self.failing_benchmarks:
            raise RuntimeError("AkShare 超时")

    def backfill_index_constituents(self, start, end, *, progress=None):
        self.calls.append("index")
        return {"requests": 3, "failed": {}}

    def backfill_industry(self, start, end, *, progress=None):
        self.calls.append("industry")
        return {"snapshots": 1, "failed": {}}


@pytest.fixture(autouse=True)
def small_batches(monkeypatch):
    monkeypatch.setattr(daily_update, "BATCH", 2)


def test_a_holiday_or_bars_not_yet_published_download_nothing(tmp_path):
    for provider, market in ((Provider(trading=False), "closed"), (Provider(published=False), "not_ready")):
        service = Service(provider)
        result = DailyUpdate(service, tmp_path / f"{market}.json").run(TODAY)
        assert result["market"] == market and service.calls == [] and provider.closed >= 1   # 还会问一次前几天的交易日历


def test_a_trading_day_updates_every_listed_stock_and_the_rest_in_order(tmp_path):
    service, beats, locked = Service(), [], []

    @contextmanager
    def lock():
        locked.append(1)
        yield

    result = DailyUpdate(service, tmp_path / "state.json", heartbeat=lambda: beats.append(1), lock=lock).run(TODAY)
    assert result["market"] == "updated" and result["errors"] == {}
    # 退市已久的、还没上市的、北交所的（BaoStock 没有）不下载；新上市的从头下载全部历史，其余的从各自最后一根 K 线接着下载。
    assert service.fetched == [(date(2015, 1, 5), ["E.SZ"]), (TODAY, ["A.SZ", "B.SZ"]), (TODAY, ["C.SZ", "D.SZ"])]
    assert service.calls == ["security_master", "bars", "bars", "bars", "actions", "repair_benchmarks", "benchmark:000300.SH", "benchmark:000905.SH",
                             "index", "industry", "universe", "settlements"]
    assert len(locked) == 3                                  # 每批下载都和手动更新互斥
    assert len(beats) >= 5                                   # 每只股票都报一次平安
    assert result["steps"]["daily_bars"]["symbols"] == 5 and result["steps"]["daily_bars"]["new_listings"] == 1


def test_a_failed_step_is_reported_the_rest_still_run_and_a_rerun_only_redoes_it(tmp_path):
    service = Service(failing_benchmarks={"000905.SH"})
    state = tmp_path / "state.json"
    first = DailyUpdate(service, state).run(TODAY)
    assert list(first["errors"]) == ["benchmarks"] and "000905.SH" in first["errors"]["benchmarks"]
    assert service.calls[-4:] == ["index", "industry", "universe", "settlements"]   # 后面的步骤照常
    service.calls.clear()
    service.failing_benchmarks.clear()
    second = DailyUpdate(service, state).run(TODAY)
    assert second["errors"] == {} and service.calls == ["repair_benchmarks", "benchmark:000300.SH", "benchmark:000905.SH"]


def test_a_rerun_skips_the_bar_batches_already_saved(tmp_path):
    service = Service(failing_symbols={"C.SZ", "D.SZ"})                     # 这一批逐只重试也都失败
    state = tmp_path / "state.json"
    first = DailyUpdate(service, state).run(TODAY)
    assert "daily_bars" in first["errors"] and "第 3 批" in first["errors"]["daily_bars"]
    service.fetched.clear()
    service.failing_symbols.clear()
    assert DailyUpdate(service, state).run(TODAY)["errors"] == {}
    assert service.fetched == [(TODAY, ["C.SZ", "D.SZ"])]
    # 换了一天，从头开始。
    service.fetched.clear()
    DailyUpdate(service, state).run(TODAY + timedelta(days=3))
    assert len(service.fetched) == 3


def test_one_bad_stock_does_not_hold_back_the_rest_of_its_batch(tmp_path):
    service = Service(failing_symbols={"B.SZ"})
    state = tmp_path / "state.json"
    first = DailyUpdate(service, state).run(TODAY)
    assert (TODAY, ["A.SZ"]) in service.fetched and (TODAY, ["C.SZ", "D.SZ"]) in service.fetched
    assert "1 只股票没有更新（B.SZ）" in first["errors"]["daily_bars"]
    service.fetched.clear()
    service.failing_symbols.clear()
    assert DailyUpdate(service, state).run(TODAY)["errors"] == {}
    assert service.fetched == [(TODAY, ["B.SZ"])]                         # 只补没更新的那一只


def test_three_failed_batches_in_a_row_stop_the_download(tmp_path, monkeypatch):
    monkeypatch.setattr(daily_update, "BATCH", 1)
    service = Service(failing_symbols={"E.SZ", "A.SZ", "B.SZ"})
    result = DailyUpdate(service, tmp_path / "state.json").run(TODAY)
    assert "连续几批失败" in result["errors"]["daily_bars"] and service.fetched == []


def test_the_background_job_runs_the_daily_update_and_records_its_result(tmp_path, monkeypatch):
    service = Service()
    service.repository.root = tmp_path / "market"
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: service)
    folder = tmp_path / "jobs" / "job"
    folder.mkdir(parents=True)
    job = {"config": "configs/app.yaml", "start_date": TODAY.isoformat(), "end_date": TODAY.isoformat(), "datasets": ["daily"]}
    assert data_jobs.attempt(folder, job) == 0
    assert data_jobs.read_json(folder / "result.json")["market"] == "updated"
    assert (tmp_path / "jobs" / f"daily-{TODAY}.json").exists()            # 断点在任务目录外，重试的任务也能接着用
    service.failing_benchmarks.add("000300.SH")
    (tmp_path / "jobs" / f"daily-{TODAY}.json").unlink()
    assert data_jobs.attempt(folder, job) == 2                              # 有一步没完成：部分完成


def test_every_job_stage_has_a_stall_guard_that_is_disarmed_when_the_job_ends(tmp_path, monkeypatch):
    # 数据源卡住时既不返回也不报错：每个阶段都要有进展，否则结束进程、由守护进程续传。
    dogs = []

    class Dog:
        def __init__(self, seconds):
            self.seconds, self.feeds, self.closed = seconds, 0, False
            dogs.append(self)

        def start(self):
            pass

        def feed(self):
            self.feeds += 1

        def pause(self):
            pass

        def resume(self):
            pass

        def close(self):
            self.closed = True

    monkeypatch.setattr("quant_platform.data.full_market_backfill._ProgressWatchdog", Dog)
    service = SimpleNamespace(app={"app": {"runtime_dir": str(tmp_path)}},
                              backfill_fundamentals=lambda start, end, symbols=None, progress=None: progress("quarterly_fundamentals", 1, 1) or {"failed": {}})
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2015-01-05", "end_date": "2026-10-15", "datasets": ["fundamentals"]}
    assert data_jobs.attempt(folder, job) == 0
    assert dogs[0].seconds == data_jobs.STALL_SECONDS and dogs[0].feeds >= 2 and dogs[0].closed


# --------------------------------------------------------------------------- #
# When to start
# --------------------------------------------------------------------------- #


def at(hour, minute=0, day=TODAY):
    return datetime.combine(day, time(hour, minute), CHINA)


def run(status, market=None, finished=at(19), day=TODAY):
    return {"id": f"{day}-{status}", "datasets": ["daily"], "end_date": day.isoformat(), "status": status,
            "updated_at": finished.isoformat(), "result": {"market": market} if market else {}, "trigger": "auto"}


@pytest.mark.parametrize("records, now, start, state", [
    ([], at(17), False, "waiting"),                                          # 还没到时间
    ([], at(18, 30), True, "waiting"),
    ([], at(19, day=TODAY + timedelta(days=1)), False, "closed"),             # 星期六
    ([run("RUNNING")], at(19), False, "running"),
    ([{"id": "x", "datasets": ["fundamentals"], "status": "RUNNING", "end_date": "2026-10-15"}], at(19), False, "waiting"),  # 等别的任务
    ([run("SUCCESS", "updated")], at(20), False, "done"),
    ([run("SUCCESS", "closed")], at(20), False, "closed"),                    # 节假日
    ([run("STOPPED")], at(20), False, "done"),                               # 管理员停了，当天不再自动启动
    ([run("SUCCESS", "not_ready", finished=at(19))], at(19, 10), False, "waiting"),   # 行情没发布：30 分钟后再试
    ([run("SUCCESS", "not_ready", finished=at(19))], at(19, 31), True, "waiting"),
    ([run("PARTIAL", "updated", finished=at(19))], at(19, 40), True, "waiting"),     # 有一步没完成：再试
    ([run("INTERRUPTED", finished=at(19))], at(19, 40), True, "waiting"),
    ([run("SUCCESS", "not_ready", finished=at(19 + i)) for i in range(4)], at(23), False, "failed"),  # 试了 4 次
    ([run("FAILED", finished=at(22))], at(23, 31), False, "failed"),           # 太晚了
    ([run("SUCCESS", "updated", day=TODAY - timedelta(days=1))], at(19), True, "waiting"),  # 昨天的不算
])
def test_when_the_daily_update_starts(records, now, start, state):
    decision = decide(records, now, at=time(18, 30))
    assert (decision.start, decision.state) == (start, state), decision.text


def test_it_can_be_turned_off_and_says_why_it_waits():
    assert decide([], at(19), at=time(18, 30), on=False).state == "disabled"
    assert decide([], at(17), at=time(18, 30)).text == "今天 18:30 以后自动更新"
    text = decide([run("SUCCESS", "not_ready", finished=at(19))], at(19, 10), at=time(18, 30)).text
    assert text == "今天的行情还没有发布，19:30 再试"


class Jobs:
    def __init__(self, records=(), busy=False):
        self._records, self.busy, self.started = list(records), busy, []

    def records(self):
        return self._records

    def start(self, start, end, datasets, symbols=None, trigger="admin"):
        if self.busy:
            raise RuntimeError("已有全市场回填任务运行。")
        self.started.append((start, end, datasets, trigger))
        job = {"id": "new", "datasets": datasets, "end_date": end.isoformat(), "status": "STARTING", "trigger": trigger}
        self._records.insert(0, job)
        return job


def test_the_scheduler_starts_one_automatic_update_and_tolerates_a_race(monkeypatch):
    monkeypatch.setattr(daily_schedule, "update_time", lambda: time(18, 30))
    jobs = Jobs()
    scheduler = DailyScheduler(jobs)
    assert not scheduler.tick(at(18))
    assert scheduler.tick(at(18, 31)) and jobs.started == [(TODAY, TODAY, ["daily"], "auto")]
    assert not scheduler.tick(at(18, 32))                 # 已经在跑
    assert not DailyScheduler(Jobs(busy=True)).tick(at(19))   # 另一个进程刚启动了任务


def test_the_status_says_what_the_last_update_did(monkeypatch):
    monkeypatch.setattr(daily_schedule, "update_time", lambda: time(18, 30))
    done = run("PARTIAL", "updated", finished=at(19))
    done["result"].update(steps={"daily_bars": {"symbols": 5300, "new_listings": 2}}, errors={"benchmarks": "000905.SH：超时"})
    status = daily_schedule.status([done], at(19, 5))
    assert status["state"] == "waiting" and status["text"] == "上次更新没有完成，19:30 再试"
    assert status["last"]["summary"] == "更新了 5,300 只股票的行情，其中 2 只是新上市，1 项没有完成"
    assert status["last"]["errors"] == ["指数行情：000905.SH：超时"]


# --------------------------------------------------------------------------- #
# Who can download
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    days = pd.bdate_range("2026-10-12", "2026-10-15")
    repo.save_table("daily_bars", pd.DataFrame([
        {"symbol": symbol, "trade_date": day, "raw_open": 1.0, "raw_close": 1.0, "adj_factor": 1.0}
        for symbol in ("000001.SZ", "600519.SH") for day in (days if symbol == "000001.SZ" else days[:-1])]))
    repo.save_table("security_master", pd.DataFrame({"symbol": ["000001.SZ", "600519.SH", "000002.SZ"],
                                                     "delist_date": [None, None, "2024-01-02"]}))
    jobs = Jobs()
    monkeypatch.setattr(workspace, "_data_jobs", lambda: jobs)
    monkeypatch.setattr(workspace, "market_repository", lambda: repo)
    app = FastAPI()
    app.include_router(workspace.router)
    app.state.user = {"id": 1, "is_admin": False}
    app.dependency_overrides[get_current_user] = lambda: app.state.user
    test_client = TestClient(app)
    test_client.jobs = jobs
    return test_client


def test_every_user_sees_the_daily_update_status_and_how_far_the_data_goes(client):
    body = client.get("/api/v1/data-center/daily-update").json()
    assert body["data"] == {"latest_date": "2026-10-15", "stocks_on_latest": 1, "listed": 2}
    assert {"enabled", "time", "state", "text", "last"} <= set(body) and "job_id" not in body


def test_only_an_admin_downloads_data_or_changes_the_data_services(client):
    for method, path, payload in [
        ("post", "/api/v1/data-center/update", {}),
        ("post", "/api/v1/data-center/market/600519/update", {"start_date": "2026-10-01", "end_date": "2026-10-09"}),
        ("get", "/api/v1/data-center/jobs", None),
        ("post", "/api/v1/data-center/jobs/start", {"start_date": "2026-01-05", "end_date": "2026-10-09", "datasets": ["bars"]}),
        ("post", "/api/v1/data-center/jobs/x/stop", {}),
        ("get", "/api/v1/data-center/jobs/x/log", None),
        ("post", "/api/v1/data-center/daily-update/run", {}),
        ("post", "/api/v1/xtick/credentials", {"token": "t", "base_url": "http://example.test"}),
        ("post", "/api/v1/xtick/request", {"url": "/doc/test"}),
    ]:
        response = getattr(client, method)(path, **({"json": payload} if payload is not None else {}))
        assert response.status_code == 403, path
    assert client.jobs.started == []
    client.app.state.user = {"id": 1, "is_admin": True}
    assert client.post("/api/v1/data-center/daily-update/run").status_code == 201
    assert client.jobs.started[0][2:] == (["daily"], "admin")
    assert "job_id" in client.get("/api/v1/data-center/daily-update").json()
