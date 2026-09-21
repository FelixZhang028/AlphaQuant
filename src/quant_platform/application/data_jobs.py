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


def now():
    return datetime.now(UTC).isoformat()


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
    def __init__(self, directory, config="configs/app.yaml"):
        self.directory = Path(directory).resolve()
        self.config = str(Path(config).resolve())
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
            records.append(job)
        return records

    def active(self):
        return next(
            (r for r in self.records() if r["status"] in ("RUNNING", "RETRYING", "STARTING")), None
        )

    def start(self, start_date, end_date, datasets):
        if start_date > end_date or end_date > date.today():
            raise ValueError("日期范围无效，结束日期不能晚于今天。")
        if not datasets or not set(datasets) <= {"bars", "actions", "derived"}:
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
                config=self.config,
                cwd=str(Path.cwd()),
                status="STARTING",
                created_at=now(),
                retries=0,
            )
            write_json(folder / "job.json", job)
            options = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            try:
                with (folder / "output.log").open("ab") as log:
                    process = subprocess.Popen(
                        [sys.executable, "-u", "-m", MODULE, str(folder)],
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        cwd=job["cwd"],
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                        **options,
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
    from quant_platform.application.data_service import DataCenterService

    checkpoint_path = None

    def progress(stage, done, total):
        checkpoint = read_json(checkpoint_path) if checkpoint_path else {}
        failures = len(checkpoint.get(stage, {}).get("failed", {}))
        write_json(
            folder / "progress.json",
            dict(stage=stage, done=done, failed=failures, total=total, updated_at=now()),
        )
        print(f"{stage}: {done}/{total}", flush=True)
        if (folder / "stop").exists():
            raise SystemExit(130)

    progress("security_master", 0, 1)
    service = DataCenterService(job["config"])
    checkpoint_path = Path(str(service.app.get("app", {}).get("runtime_dir", "runtime"))) / (
        "full_market_backfill_state.json"
    )
    result = service.run_closed_loop(
        date.fromisoformat(job["start_date"]),
        date.fromisoformat(job["end_date"]),
        resume=True,
        skip_bars="bars" not in job["datasets"],
        skip_actions="actions" not in job["datasets"],
        skip_derived="derived" not in job["datasets"],
        progress=progress,
        watchdog_timeout=600.0,
    )
    write_json(folder / "result.json", result)
    failed = any(result.get(key, {}).get("failed") for key in ("daily_bars", "corporate_actions"))
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
