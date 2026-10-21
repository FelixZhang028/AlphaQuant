"""数据源被拉黑、白天运行每日更新时的行为：放慢请求、被拒绝就停下、先补齐前几天、把结果说清楚。"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from app.quant import daily_schedule, fundamentals_schedule
from app.quant.daily_schedule import CHINA, decide, outcome_text
from quant_platform.application.daily_update import DailyUpdate
from quant_platform.application.data_jobs import BLOCKED_REASON, NETWORK_REASON, DataJobs, failure_reason
from quant_platform.core.exceptions import DataSourceBlocked, DataUnavailableError
from quant_platform.data.providers import baostock_provider
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider
from quant_platform.data.router import DataRouter
from test_daily_update import TODAY, Provider, Service

BLOCKED = SimpleNamespace(error_code="10001011", error_msg="黑名单用户，请与管理员联系")
OK = SimpleNamespace(error_code="0", error_msg="", get_data=lambda: pd.DataFrame({"calendar_date": ["2026-10-19"]}))


class Client:
    def __init__(self, login=OK, query=OK):
        self.logins, self.queries, self._login, self._query = 0, 0, login, query

    def login(self):
        self.logins += 1
        return self._login

    def logout(self):
        pass

    def query_trade_dates(self, start_date, end_date):
        self.queries += 1
        return self._query


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_BAOSTOCK_INTERVAL", "0")


def test_a_blacklisted_server_stops_at_once_instead_of_retrying():
    client = Client(login=BLOCKED)
    with pytest.raises(DataSourceBlocked, match="黑名单"):
        BaoStockDataProvider(client=client).login()
    assert client.logins == 1                                       # 不再重试第二、第三次
    client = Client(query=BLOCKED)
    with pytest.raises(DataSourceBlocked):
        BaoStockDataProvider(client=client).get_trade_calendar(date(2026, 10, 1), date(2026, 10, 19))
    assert client.queries == 1
    assert issubclass(DataSourceBlocked, DataUnavailableError)      # 以前捕获“数据不可用”的地方照样能处理


def test_requests_are_spaced_out(monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_BAOSTOCK_INTERVAL", "0.05")
    monkeypatch.setattr(baostock_provider, "_last_request", 0.0)
    slept = []
    monkeypatch.setattr(baostock_provider.time, "sleep", lambda seconds: slept.append(seconds))
    provider = BaoStockDataProvider(client=Client())
    for _ in range(3):
        provider.get_trade_calendar(date(2026, 10, 1), date(2026, 10, 19))
    # 机器开机很久时 time.monotonic() 很大，相减会有一点浮点误差（例如 0.05000000004）
    assert len(slept) >= 2 and all(0 < s <= 0.05 + 1e-6 for s in slept)
    monkeypatch.setenv("FELLOWQUANT_BAOSTOCK_INTERVAL", "oops")
    assert baostock_provider.request_interval() == baostock_provider.DEFAULT_INTERVAL


def test_the_router_keeps_the_blocked_reason():
    class Blocked:
        def get_history(self, **kwargs):
            raise DataSourceBlocked("黑名单")

    router = DataRouter({"baostock": Blocked()}, {"daily_bars": ["baostock"]})
    with pytest.raises(DataSourceBlocked):
        router.fetch("daily_bars", "get_history")


class CalendarProvider(Provider):
    """Today's bars are not out; the trading days before today are."""

    def __init__(self, days):
        super().__init__(trading=True, published=False)
        self.days = days

    def get_trade_calendar(self, start, end):
        if start == end:                                             # 问的是今天
            return pd.DataFrame({"calendar_date": [start.isoformat()], "is_trading_day": ["1"]})
        frame = pd.DataFrame({"calendar_date": [d.isoformat() for d in self.days if start <= d <= end]})
        frame["is_trading_day"] = "1"
        return frame


def test_during_the_day_it_catches_up_to_the_last_published_trading_day(tmp_path):
    yesterday = TODAY - timedelta(days=1)
    service = Service(CalendarProvider([TODAY - timedelta(days=3), yesterday]))     # 本地只到 10-15
    result = DailyUpdate(service, tmp_path / "state.json").run(TODAY + timedelta(days=0))
    # 本地 summary 到 2026-10-15，最近发布的交易日是 10-15：已经是最新的
    assert result["market"] == "not_ready" and result.get("up_to_date") is True and "caught_up" not in result
    later = TODAY + timedelta(days=3)                                               # 下周一，本地还停在 10-15
    service = Service(CalendarProvider([TODAY, later - timedelta(days=0)]))
    result = DailyUpdate(service, tmp_path / "state2.json").run(later)
    assert result["caught_up"] == TODAY.isoformat() and result["trade_date"] == TODAY.isoformat()
    assert "bars" in service.calls and service.fetched and all(start == TODAY for start, _ in service.fetched if start != date(2015, 1, 5))


def test_a_block_in_the_middle_stops_the_remaining_steps(tmp_path):
    service = Service()

    def blocked(*args, **kwargs):
        raise DataSourceBlocked("黑名单用户")

    service.update_market_data = blocked
    result = DailyUpdate(service, tmp_path / "state.json").run(TODAY)
    assert result["blocked"] is True and "daily_bars" in result["errors"]
    assert "actions" not in service.calls and "industry" not in service.calls      # 后面的步骤没有再请求


def test_failure_reasons_are_read_from_the_log(tmp_path):
    assert failure_reason("... BaoStock login failed [10001011]: 黑名单用户，请与管理员联系") == (BLOCKED_REASON, True)
    assert failure_reason("BaoStock login failed [10002007]: 网络接收错误。") == (NETWORK_REASON, False)
    assert failure_reason("Traceback\nValueError: 证券主表为空") == ("ValueError: 证券主表为空", False)
    assert failure_reason("") == ("", False)
    folder = tmp_path / "jobs" / "20261019183043-aaaa"
    folder.mkdir(parents=True)
    (folder / "job.json").write_text('{"id": "20261019183043-aaaa", "status": "FAILED", "datasets": ["daily"], "pid": null}', encoding="utf-8")
    (folder / "output.log").write_text("login failed [10001011]: 黑名单用户，请与管理员联系", encoding="utf-8")
    record = DataJobs(tmp_path / "jobs", "config.yaml").records()[0]
    assert record["blocked"] is True and record["failure"] == BLOCKED_REASON


def at(day, hour, minute=0):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CHINA)


def test_a_blocked_update_is_not_retried_the_same_day():
    record = {"datasets": ["daily"], "end_date": TODAY.isoformat(), "status": "FAILED", "blocked": True,
              "created_at": at(TODAY, 18, 30).isoformat(), "updated_at": at(TODAY, 18, 31).isoformat()}
    decision = decide([record], at(TODAY, 20))
    assert decision.start is False and decision.state == "failed" and "黑名单" in decision.text
    saturday = date(2026, 10, 17)
    auto = {"datasets": ["fundamentals"], "trigger": "auto", "status": "FAILED", "blocked": True,
            "created_at": at(saturday, 10).isoformat(), "updated_at": at(saturday, 10, 5).isoformat()}
    assert fundamentals_schedule.decide([auto], at(saturday, 14)).start is False


def test_the_outcome_says_what_actually_happened():
    ok = {"status": "SUCCESS"}
    assert outcome_text(ok, {"market": "not_ready", "steps": {}}) == "当天的行情还没有发布，没有下载数据"
    assert outcome_text(ok, {"market": "not_ready", "up_to_date": True}) == "当天的行情还没有发布，本地已经有最近一个交易日的行情，没有下载数据"
    assert outcome_text(ok, {"market": "not_ready", "caught_up": "2026-10-19", "steps": {"daily_bars": {}}}) == "当天的行情还没有发布，先补到 2026-10-19"
    assert outcome_text(ok, {"market": "updated", "steps": {"daily_bars": {}}}) == "已更新到当天"
    failed = {"status": "FAILED", "failure": BLOCKED_REASON}
    assert outcome_text(failed, {}) == "没有完成：" + BLOCKED_REASON
    partial = {"status": "PARTIAL", "failure": BLOCKED_REASON}
    assert "中途被数据源拒绝" in outcome_text(partial, {"market": "updated", "steps": {"security_master": {}}, "errors": {"daily_bars": "x"}, "blocked": True})
    last = daily_schedule.status([{"datasets": ["daily"], "end_date": TODAY.isoformat(), "status": "SUCCESS", "trigger": "admin",
                                   "result": {"market": "not_ready", "caught_up": "2026-10-15", "trade_date": "2026-10-15",
                                              "steps": {"daily_bars": {"symbols": 5200}}, "errors": {}},
                                   "created_at": at(TODAY, 9).isoformat(), "updated_at": at(TODAY, 9, 20).isoformat()}],
                                 now=at(TODAY, 10))["last"]
    assert last["data_date"] == "2026-10-15" and last["caught_up"] == "2026-10-15" and last["outcome"].startswith("当天的行情还没有发布，先补到")


def test_a_blocked_attempt_ends_the_job_instead_of_retrying(tmp_path, monkeypatch):
    # 2026-10-20：被拉黑以后，任务每 60 秒重试一次、每次都重新登录，拉黑一直解除不了。
    from quant_platform.application import data_jobs

    def blocked(folder, job, watchdog):
        raise DataSourceBlocked("黑名单用户")

    monkeypatch.setattr(data_jobs, "_attempt", blocked)
    assert data_jobs.attempt(tmp_path, {}) == data_jobs.BLOCKED_EXIT

    folder = tmp_path / "jobs" / "20261020212810-aaaa"
    folder.mkdir(parents=True)
    data_jobs.write_json(folder / "job.json", {"id": folder.name, "status": "STARTING", "cwd": str(tmp_path)})
    started = []

    class Child:
        pid = 1

        def wait(self):
            started.append(1)
            return data_jobs.BLOCKED_EXIT

    monkeypatch.setattr(data_jobs.subprocess, "Popen", lambda *args, **kwargs: Child())
    monkeypatch.setattr(data_jobs.time, "sleep", lambda seconds: None)
    data_jobs.supervise(folder)
    job = data_jobs.read_json(folder / "job.json")
    assert len(started) == 1 and job["status"] == "FAILED" and job["blocked"] is True
