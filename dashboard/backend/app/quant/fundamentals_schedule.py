"""财报季每周六自动更新财务数据。

财报只在几个时间段集中发布（年报和一季报 1～4 月，半年报 7～8 月，三季报 10 月），平时不会有新的。规则（北京时间）：
- 财报季的每个周六 10:00 以后启动一次：1、2、3、4、7、8、10 月的每个周六，以及 5、9、11 月的第一个周六
  （赶上截止日最后几天发布的公司）；
- 只请求最近 ``WINDOW_DAYS`` 天里还没有的报告期，已经有的不会重复下载；
- 失败或意外中断时 1 小时后再试，当天最多 ``MAX_RUNS`` 次；管理员停止了就当天不再启动；
- 周六不是交易日，不会和每日行情更新同时运行；有别的数据任务在运行时等它结束；
- ``FELLOWQUANT_FUNDAMENTALS_UPDATE=off`` 关闭（管理员仍可以手动更新）。
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import date, datetime, time, timedelta
from typing import Any

from .daily_schedule import ACTIVE, CHINA, Decision, china_now

logger = logging.getLogger("uvicorn.error")

DATASET = "fundamentals"
RUN_AT = time(10, 0)
WINDOW_DAYS = 450            # 覆盖最近 5 个报告期，包括晚到的年报
MAX_RUNS = 3
RETRY_AFTER = timedelta(hours=1)
CHECK_SECONDS = 600
SATURDAY = 5
SEASON_MONTHS = {1, 2, 3, 4, 7, 8, 10}
CATCH_UP_MONTHS = {5, 9, 11}  # 只有第一个周六


def enabled() -> bool:
    return os.getenv("FELLOWQUANT_FUNDAMENTALS_UPDATE", "on").strip().lower() not in ("0", "off", "false", "no")


def runs_day(day: date) -> bool:
    """这一天是不是自动更新财务数据的日子。"""

    if day.weekday() != SATURDAY:
        return False
    return day.month in SEASON_MONTHS or (day.month in CATCH_UP_MONTHS and day.day <= 7)


def next_run(today: date) -> date:
    day = today
    while not runs_day(day):
        day += timedelta(days=1)
    return day


def window(today: date) -> tuple[date, date]:
    return today - timedelta(days=WINDOW_DAYS), today


def _china_day(record: dict[str, Any]) -> date | None:
    try:
        return datetime.fromisoformat(str(record.get("created_at"))).astimezone(CHINA).date()
    except ValueError:
        return None


def _finished_at(record: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(record.get("updated_at") or record.get("created_at"))).astimezone(CHINA)
    except ValueError:
        return None


def auto_runs(records: list[dict[str, Any]], day: date | None = None) -> list[dict[str, Any]]:
    """自动启动的财务数据更新，新的在前；给了 ``day`` 就只要那一天的。"""

    runs = [r for r in records if r.get("datasets") == [DATASET] and r.get("trigger") == "auto"]
    return [r for r in runs if _china_day(r) == day] if day else runs


def decide(records: list[dict[str, Any]], now: datetime, *, on: bool = True) -> Decision:
    today = now.date()
    runs = auto_runs(records, today)
    last = runs[0] if runs else None
    if last and last.get("status") in ACTIVE:
        return Decision(False, "running", "正在更新财务数据")
    if not on:
        return Decision(False, "disabled", "自动更新已关闭（FELLOWQUANT_FUNDAMENTALS_UPDATE=off），由管理员手动更新")
    if not runs_day(today):
        return Decision(False, "waiting", f"下一次自动更新：{next_run(today).isoformat()}（周六）")
    if now.time() < RUN_AT:
        return Decision(False, "waiting", f"今天 {RUN_AT:%H:%M} 以后自动更新")
    if last is not None:
        status = last.get("status")
        later = next_run(today + timedelta(days=1)).isoformat()
        if status == "STOPPED":
            return Decision(False, "done", f"管理员停止了今天的更新；下一次 {later}")
        if status in ("SUCCESS", "PARTIAL"):
            return Decision(False, "done", f"今天已经更新；下一次 {later}")
        if last.get("blocked"):
            return Decision(False, "failed", f"数据源 BaoStock 暂时拒绝了这台服务器（请求太多），今天不再自动重试；下一次 {later}")
        if len(runs) >= MAX_RUNS:
            return Decision(False, "failed", f"今天试了 {len(runs)} 次都没有完成；下一次 {later}")
        finished = _finished_at(last)
        if finished is not None and now - finished < RETRY_AFTER:
            return Decision(False, "waiting", f"上次没有完成，{(finished + RETRY_AFTER):%H:%M} 再试")
    if any(r.get("status") in ACTIVE for r in records):
        return Decision(False, "waiting", "等别的数据任务完成后再更新")
    return Decision(True, "waiting", "马上开始更新财务数据")


def status(records: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """管理后台看的：自动更新的状态和上一次自动更新的结果。"""

    now = now or china_now()
    decision = decide(records, now, on=enabled())
    finished = next((r for r in auto_runs(records) if r.get("status") not in ACTIVE), None)
    last = None
    if finished is not None:
        result = finished.get("result") or {}
        last = {"status": finished.get("status"), "finished_at": finished.get("updated_at") or finished.get("created_at"),
                "failure": finished.get("failure", ""), "blocked": bool(finished.get("blocked")),
                "start_date": finished.get("start_date"), "end_date": finished.get("end_date"), "result": result}
    return {"enabled": enabled(), "state": decision.state, "text": decision.text, "next_run": next_run(now.date()).isoformat(),
            "window_days": WINDOW_DAYS, "last": last}


class FundamentalsScheduler:
    """Checks every ten minutes in a daemon thread; ``jobs`` is a ``DataJobs``."""

    def __init__(self, jobs: Any) -> None:
        self.jobs = jobs
        self._stop = threading.Event()

    def tick(self, now: datetime | None = None) -> bool:
        now = now or china_now()
        if not decide(self.jobs.records(), now, on=enabled()).start:
            return False
        start, end = window(now.date())
        try:
            self.jobs.start(start, end, [DATASET], trigger="auto")
        except (RuntimeError, ValueError) as exc:  # 别的进程刚启动了任务
            logger.info("财务数据自动更新没有启动：%s", exc)
            return False
        logger.info("财务数据自动更新已启动（%s ~ %s）", start, end)
        return True

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - 检查失败不能让线程退出
                logger.exception("财务数据自动更新检查失败")

    def start(self) -> None:
        threading.Thread(target=self._loop, name="fundamentals-update", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
