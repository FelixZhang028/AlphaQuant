"""Persistent, detached full-market jobs shared by all web sessions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from functools import wraps
from pathlib import Path

MODULE = "quant_platform.application.data_jobs"
DATASETS = {"bars", "actions", "derived", "indicators", "fundamentals", "industry", "index_constituents", "bar_gaps", "action_gaps", "daily"}
# 除全市场日线（自带看门狗）以外的阶段：这么久没有进展就结束进程，由守护进程从断点续传。
# 数据源偶尔会卡住既不返回也不报错，没有这个保护时任务会一直挂着。
STALL_SECONDS = 900.0


def now():
    return datetime.now(UTC).isoformat()


# 没有完成的任务：从日志里找出原因，翻成给人看的话。被数据源拒绝（黑名单）时要单独说明，
# 并且当天不要再自动重试——每次重试都会让拉黑持续更久。
BLOCKED_REASON = ("数据源 BaoStock 暂时拒绝了这台服务器（被列入黑名单），通常是短时间内请求太多。"
                  "请过几个小时再试，这段时间不要反复运行数据更新。")
NETWORK_REASON = "连不上数据源 BaoStock（网络错误），稍后会自动重试。"
LOG_TAIL_BYTES = 64000


def failure_reason(text):
    """``(reason, blocked)`` from the end of a job's log; ``("", False)`` when nothing is recognised."""

    if not text:
        return "", False
    if "黑名单" in text or "10001011" in text:
        return BLOCKED_REASON, True
    if "网络接收错误" in text or "ConnectionError" in text or "timed out" in text:
        return NETWORK_REASON, False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    errors = [line for line in lines if "Error" in line or "错误" in line or "失败" in line]
    last = (errors or lines or [""])[-1]
    try:
        from quant_platform.core.diagnostics import redact_text

        last = redact_text(last)
    except Exception:  # noqa: BLE001 - 脱敏失败时只截短
        pass
    return last[:200], False


def _log_tail(folder):
    path = folder / "output.log"
    if not path.exists():
        return ""
    with path.open("rb") as handle:
        handle.seek(max(0, path.stat().st_size - LOG_TAIL_BYTES))
        return handle.read().decode("utf-8", errors="replace")


@contextmanager
def exclusive(path):
    """OS lock, automatically released even if a process crashes."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("已有数据任务运行，请等待完成后再试。") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def serialized_update(method):
    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with exclusive(self.repository.root / ".update.lock"):
            return method(self, *args, **kwargs)

    return wrapped


def launch_detached(command, **options):
    """Start a job process that outlives whatever started it.

    On Windows the backend may run inside a job object (the launcher's, which closes all its
    processes when the launcher stops). A data download must not die with it, so the process
    breaks away from that job; if the job does not allow it, it starts inside the job as before.
    """

    if os.name != "nt":
        return subprocess.Popen(command, start_new_session=True, **options)
    try:
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB, **options)
    except PermissionError:
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW, **options)


def write_json(path, value):
    temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    os.replace(temporary, path)


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


class DataJobs:
    def __init__(self, directory, config="configs/app.yaml", cwd=None):
        self.directory = Path(directory).resolve()
        self.config = str(Path(config).resolve())
        # 子进程工作目录：vendored quant_platform 的导入与 yaml 相对路径都
        # 以 backend 根为基准；API 服务器可能从其他目录启动，需显式指定。
        self.cwd = str(Path(cwd).resolve()) if cwd else str(Path.cwd())
        self.directory.mkdir(parents=True, exist_ok=True)

    def records(self):
        records = []
        for path in sorted(self.directory.glob("*/job.json"), reverse=True):
            job = read_json(path)
            if not job:
                continue
            if job["status"] in ("RUNNING", "RETRYING", "STARTING"):
                if not alive(job.get("pid")) and not alive(job.get("child_pid")):
                    job["status"] = "INTERRUPTED"
            job["progress"] = read_json(path.parent / "progress.json")
            job["stopping"] = (path.parent / "stop").exists()
            # 结果（每一步下载了多少、哪里失败）给页面看；任务还没结束时为空。
            job["result"] = read_json(path.parent / "result.json")
            if job["status"] in ("FAILED", "INTERRUPTED", "PARTIAL"):
                reason, blocked = failure_reason(_log_tail(path.parent))
                if (job.get("result") or {}).get("blocked"):
                    reason, blocked = BLOCKED_REASON, True
                job["failure"], job["blocked"] = reason, blocked
            records.append(job)
        return records

    def active(self):
        return next(
            (r for r in self.records() if r["status"] in ("RUNNING", "RETRYING", "STARTING")), None
        )

    def start(self, start_date, end_date, datasets, symbols=None, trigger="admin"):
        """启动后台任务。``symbols`` 只对财务数据生效：限定下载哪些股票，不给就是全部。
        ``trigger``：``auto``（每天自动更新）或 ``admin``（管理员手动）。"""

        if start_date > end_date or end_date > date.today():
            raise ValueError("日期范围无效，结束日期不能晚于今天。")
        if not datasets or not set(datasets) <= DATASETS:
            raise ValueError("请至少选择一个有效的数据集。")
        with exclusive(self.directory / ".launch.lock"):
            if self.active():
                raise RuntimeError("已有全市场回填任务运行。")
            identifier = datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:8]
            folder = self.directory / identifier
            folder.mkdir()
            job = dict(
                id=identifier,
                start_date=str(start_date),
                end_date=str(end_date),
                datasets=list(datasets),
                symbols=list(symbols) if symbols else None,
                config=self.config,
                cwd=self.cwd,
                status="STARTING",
                created_at=now(),
                retries=0,
                trigger=trigger,
            )
            write_json(folder / "job.json", job)
            try:
                with (folder / "output.log").open("ab") as log:
                    process = launch_detached(
                        [sys.executable, "-u", "-m", MODULE, str(folder)],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        cwd=job["cwd"],
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    )
                job["pid"] = process.pid
                write_json(folder / "job.json", job)
            except Exception:
                job["status"] = "FAILED"
                write_json(folder / "job.json", job)
                raise
            return job

    def stop(self, identifier):
        if not any(r["id"] == identifier for r in self.records()):
            raise ValueError("任务不存在。")
        (self.directory / identifier / "stop").touch()

    def log(self, identifier):
        if not any(r["id"] == identifier for r in self.records()):
            return ""
        path = self.directory / identifier / "output.log"
        if not path.exists():
            return ""
        with path.open("rb") as handle:
            handle.seek(max(0, path.stat().st_size - 32000))
            return handle.read().decode("utf-8", errors="replace")


def attempt(folder, job):
    from quant_platform.data.full_market_backfill import _ProgressWatchdog

    watchdog = _ProgressWatchdog(STALL_SECONDS)
    watchdog.start()
    try:
        return _attempt(folder, job, watchdog)
    finally:
        watchdog.close()


def _attempt(folder, job, watchdog):
    from quant_platform.application.data_service import DataCenterService

    checkpoint_path = None

    def progress(stage, done, total):
        watchdog.feed()
        checkpoint = read_json(checkpoint_path) if checkpoint_path else {}
        failures = len(checkpoint.get(stage, {}).get("failed", {}))
        write_json(
            folder / "progress.json",
            dict(stage=stage, done=done, failed=failures, total=total, updated_at=now()),
        )
        print(f"{stage}: {done}/{total}", flush=True)
        if (folder / "stop").exists():
            raise SystemExit(130)

    if "daily" in job["datasets"]:
        from quant_platform.application.daily_update import DailyUpdate

        def heartbeat():
            watchdog.feed()
            if (folder / "stop").exists():
                raise SystemExit(130)

        service = DataCenterService(job["config"])
        # 断点按日期存在任务目录外面：同一天重新启动的任务接着上次的进度。
        state = folder.parent / f"daily-{job['end_date']}.json"
        daily = DailyUpdate(service, state, heartbeat=heartbeat, progress=progress,
                            lock=lambda: exclusive(service.repository.root / ".update.lock"))
        result = daily.run(date.fromisoformat(job["end_date"]))
        write_json(folder / "result.json", result)
        return 2 if result["errors"] else 0

    progress("security_master", 0, 1)
    service = DataCenterService(job["config"])
    checkpoint_path = Path(str(service.app.get("app", {}).get("runtime_dir", "runtime"))) / (
        "full_market_backfill_state.json"
    )
    start, end = date.fromisoformat(job["start_date"]), date.fromisoformat(job["end_date"])
    result = {}
    if set(job["datasets"]) & {"bars", "actions", "derived"}:
        # 全市场日线自带看门狗（每只股票喂一次），这段时间不用外层的。
        watchdog.pause()
        result = service.run_closed_loop(
            start,
            end,
            resume=True,
            skip_bars="bars" not in job["datasets"],
            skip_actions="actions" not in job["datasets"],
            skip_derived="derived" not in job["datasets"],
            progress=progress,
            watchdog_timeout=600.0,
        )
        watchdog.resume()
    if "bar_gaps" in job["datasets"]:
        result["bar_gaps"] = service.repair_bar_gaps(start, end, progress=progress)
    if "action_gaps" in job["datasets"]:
        result["action_gaps"] = service.backfill_corporate_action_gaps(progress=progress)
    if "indicators" in job["datasets"]:
        # 放在日线之后：这次任务里刚下载的行情，估值与换手率已经跟着存好了，这里只补以前的。
        result["daily_indicators"] = service.backfill_daily_indicators(start, end, progress=progress)
    if "fundamentals" in job["datasets"]:
        result["quarterly_fundamentals"] = service.backfill_fundamentals(
            start, end, symbols=job.get("symbols"), progress=progress
        )
    if "industry" in job["datasets"]:
        result["industry"] = service.backfill_industry(start, end, progress=progress)
    if "index_constituents" in job["datasets"]:
        result["index_constituents"] = service.backfill_index_constituents(start, end, progress=progress)
    write_json(folder / "result.json", result)
    failed = any(
        result.get(key, {}).get("failed")
        for key in ("daily_bars", "corporate_actions", "daily_indicators", "quarterly_fundamentals", "industry", "index_constituents", "bar_gaps", "action_gaps")
    )
    return 2 if failed else 0


def supervise(folder):
    # The launcher publishes its PID before the worker starts changing job state.
    for _ in range(100):
        try:
            with exclusive(folder.parent / ".launch.lock"):
                job = read_json(folder / "job.json")
            break
        except RuntimeError:
            time.sleep(0.1)
    else:
        return
    try:
        for retry in range(21):
            if (folder / "stop").exists():
                job["status"] = "STOPPED"
                break
            job.update(status="RUNNING", retries=retry, updated_at=now())
            write_json(folder / "job.json", job)
            options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
            with (folder / "output.log").open("ab") as log:
                child = subprocess.Popen(
                    [sys.executable, "-u", "-m", MODULE, str(folder), "--attempt"],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cwd=job["cwd"],
                    **options,
                )
                job["child_pid"] = child.pid
                write_json(folder / "job.json", job)
                code = child.wait()
            job.update(child_pid=None, exit_code=code)
            if (folder / "stop").exists() or code == 130:
                job["status"] = "STOPPED"
                break
            if code == 0:
                job["status"] = "SUCCESS"
                break
            if code == 2:
                job["status"] = "PARTIAL"
                break
            if retry == 20:
                job["status"] = "FAILED"
                break
            job.update(status="RETRYING", updated_at=now())
            write_json(folder / "job.json", job)
            print(f"退出码 {code}，60 秒后续传（第 {retry + 1} 次重试）", flush=True)
            for _ in range(60):
                if (folder / "stop").exists():
                    break
                time.sleep(1)
    except Exception as exc:
        job.update(status="FAILED", error=str(exc))
        raise
    finally:
        job["updated_at"] = now()
        write_json(folder / "job.json", job)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--attempt", action="store_true")
    args = parser.parse_args()
    if args.attempt:
        sys.exit(attempt(args.folder, read_json(args.folder / "job.json")))
    supervise(args.folder)
