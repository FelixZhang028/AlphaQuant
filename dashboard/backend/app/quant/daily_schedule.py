"""每个交易日收盘后自动更新全市场数据，以及给页面看的更新状态。

规则（北京时间）：
- 周一到周五，到 ``FELLOWQUANT_DAILY_UPDATE_TIME``（默认 18:30）以后启动一次每日更新；
- 当天的行情还没发布、或者更新失败、意外中断时，30 分钟后再试，最多 4 次，23:30 以后不再启动；
- 不是交易日（节假日）、更新完成、或者管理员停止了当天的更新，当天就不再启动；
- 有别的数据任务在运行时等它结束。
- ``FELLOWQUANT_DAILY_UPDATE=off`` 关闭自动更新（管理员仍可以手动启动）。

多个后端进程同时检查也只会启动一次：启动任务时有文件锁，并且同一时间只能有一个数据任务。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

logger = logging.getLogger("uvicorn.error")

CHINA = timezone(timedelta(hours=8))
DEFAULT_TIME = time(18, 30)
LAST_START = time(23, 30)
RETRY_AFTER = timedelta(minutes=30)
MAX_RUNS = 4
CHECK_SECONDS = 60
ACTIVE = ("STARTING", "RUNNING", "RETRYING")
DATASET = "daily"
STEP_NAMES = {
    "security_master": "股票列表", "daily_bars": "日线行情", "corporate_actions": "分红送转记录", "benchmarks": "指数行情",
    "index_constituents": "指数成分股", "industry": "行业分类", "derived": "历史股票池",
}


def enabled() -> bool:
    return os.getenv("FELLOWQUANT_DAILY_UPDATE", "on").strip().lower() not in ("0", "off", "false", "no")


def update_time() -> time:
    raw = os.getenv("FELLOWQUANT_DAILY_UPDATE_TIME", "").strip()
    try:
        hour, minute = (int(part) for part in raw.split(":"))
        return time(hour, minute)
    except ValueError:
        return DEFAULT_TIME


def china_now() -> datetime:
    return datetime.now(CHINA)


def _finished_at(record: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(record.get("updated_at") or record.get("created_at")))
    except ValueError:
        return None


def runs_on(records: list[dict[str, Any]], day: date) -> list[dict[str, Any]]:
    """That day's daily updates, newest first (``records`` are newest first)."""

    return [r for r in records if DATASET in r.get("datasets", []) and r.get("end_date") == day.isoformat()]


@dataclass(frozen=True)
class Decision:
    start: bool
    # waiting / running / done / closed / failed / disabled
    state: str
    text: str


def decide(records: list[dict[str, Any]], now: datetime, *, at: time | None = None, on: bool = True) -> Decision:
    """Whether to start the daily update now, and what to tell the user."""

    at = at or update_time()
    day = now.date()
    runs = runs_on(records, day)
    last = runs[0] if runs else None
    if last and last.get("status") in ACTIVE:
        return Decision(False, "running", "正在更新今天的数据")
    if not on:
        return Decision(False, "disabled", "自动更新已关闭，由管理员手动更新")
    if now.weekday() >= 5:
        return Decision(False, "closed", "周末不更新，下个交易日收盘后自动更新")
    if now.time() < at:
        return Decision(False, "waiting", f"今天 {at:%H:%M} 以后自动更新")
    if last is not None:
        status, market = last.get("status"), (last.get("result") or {}).get("market")
        if status == "STOPPED":
            return Decision(False, "done", "管理员停止了今天的更新")
        if status == "SUCCESS" and market == "closed":
            return Decision(False, "closed", "今天不是交易日，不更新")
        if status == "SUCCESS" and market == "updated":
            return Decision(False, "done", "今天的数据已经更新")
        if len(runs) >= MAX_RUNS or now.time() >= LAST_START:
            reason = "行情还没有发布" if market == "not_ready" else "更新没有完成"
            return Decision(False, "failed", f"今天试了 {len(runs)} 次，{reason}；明天收盘后再更新")
        finished = _finished_at(last)
        if finished is not None and now - finished.astimezone(CHINA) < RETRY_AFTER:
            retry = (finished.astimezone(CHINA) + RETRY_AFTER).strftime("%H:%M")
            reason = "今天的行情还没有发布" if market == "not_ready" else "上次更新没有完成"
            return Decision(False, "waiting", f"{reason}，{retry} 再试")
    elif now.time() >= LAST_START:
        return Decision(False, "failed", "今天没能在 23:30 前开始更新；明天收盘后再更新")
    if any(r.get("status") in ACTIVE for r in records):
        return Decision(False, "waiting", "等别的数据任务完成后再更新")
    return Decision(True, "waiting", "马上开始更新")


class DailyScheduler:
    """Checks once a minute in a daemon thread; ``jobs`` is a ``DataJobs``."""

    def __init__(self, jobs: Any) -> None:
        self.jobs = jobs
        self._stop = threading.Event()

    def tick(self, now: datetime | None = None) -> bool:
        now = now or china_now()
        decision = decide(self.jobs.records(), now, on=enabled())
        if not decision.start:
            return False
        try:
            self.jobs.start(now.date(), now.date(), [DATASET], trigger="auto")
        except (RuntimeError, ValueError) as exc:  # 别的进程刚启动了任务
            logger.info("每日数据更新没有启动：%s", exc)
            return False
        logger.info("每日数据更新已启动（%s）", now.date())
        return True

    def _loop(self) -> None:
        while not self._stop.wait(CHECK_SECONDS):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - 检查失败不能让线程退出
                logger.exception("每日数据更新检查失败")

    def start(self) -> None:
        threading.Thread(target=self._loop, name="daily-data-update", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def _step_text(name: str, outcome: Any) -> str:
    if not isinstance(outcome, dict):
        return "完成"
    if name == "security_master" and "rows" in outcome:
        return f"{outcome['rows']:,} 只证券"
    if name == "daily_bars" and "symbols" in outcome:
        new = f"，其中新上市 {outcome['new_listings']} 只" if outcome.get("new_listings") else ""
        return f"{outcome['symbols']:,} 只股票{new}"
    if name == "benchmarks" and "symbols" in outcome:
        return f"{outcome['symbols']} 个指数"
    if name == "derived" and "universe_rows" in outcome:
        return f"历史股票池 {outcome['universe_rows']:,} 条"
    return "完成"


def step_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    """每一步的结果：完成 / 没完成（原因）/ 没有运行（例如当天不是交易日）。"""

    steps, errors = result.get("steps") or {}, result.get("errors") or {}
    items = []
    for name, label in STEP_NAMES.items():
        if name in errors:
            items.append({"key": name, "label": label, "state": "failed", "text": str(errors[name])[:300]})
        elif name in steps:
            items.append({"key": name, "label": label, "state": "done", "text": _step_text(name, steps[name])})
        else:
            items.append({"key": name, "label": label, "state": "skipped", "text": "没有运行"})
    return items


def _summary(result: dict[str, Any]) -> str:
    steps = result.get("steps") or {}
    bars = steps.get("daily_bars") or {}
    parts = []
    if bars:
        parts.append(f"更新了 {bars.get('symbols', 0):,} 只股票的行情")
        if bars.get("new_listings"):
            parts.append(f"其中 {bars['new_listings']} 只是新上市")
    errors = result.get("errors") or {}
    if errors:
        parts.append(f"{len(errors)} 项没有完成")
    return "，".join(parts)


def status(records: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
    """What the data page shows every user about the automatic update."""

    now = now or china_now()
    decision = decide(records, now, on=enabled())
    daily = [r for r in records if DATASET in r.get("datasets", [])]
    finished = next((r for r in daily if r.get("status") not in ACTIVE), None)
    last = None
    if finished is not None:
        result = finished.get("result") or {}
        last = {
            "trade_date": finished.get("end_date"),
            "status": finished.get("status"),
            "market": result.get("market"),
            "finished_at": finished.get("updated_at") or finished.get("created_at"),
            "summary": _summary(result),
            "errors": [f"{STEP_NAMES.get(name, name)}：{message}" for name, message in (result.get("errors") or {}).items()][:5],
            "steps": step_results(result),
            "trigger": finished.get("trigger", "admin"),
        }
    running = next((r for r in daily if r.get("status") in ACTIVE), None)
    return {
        "enabled": enabled(),
        "time": f"{update_time():%H:%M}",
        "state": decision.state,
        "text": decision.text,
        "last": last,
        "progress": (running or {}).get("progress") or None,
        "job_id": (running or {}).get("id"),
    }
