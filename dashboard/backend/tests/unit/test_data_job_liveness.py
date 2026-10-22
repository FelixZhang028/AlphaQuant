"""数据任务的进程早就结束、进程号被别的程序重新用了：任务不能一直显示“运行中”或“正在停止”。"""

import json
import os
from datetime import UTC, datetime, timedelta

from quant_platform.application import data_jobs
from quant_platform.application.data_jobs import DataJobs, alive, process_started_at


def write_job(root, identifier, created, stop=False, **extra):
    folder = root / identifier
    folder.mkdir(parents=True)
    job = {"id": identifier, "status": "RUNNING", "datasets": ["fundamentals"], "pid": 111, "child_pid": 222,
           "created_at": created.isoformat(), "updated_at": created.isoformat(), **extra}
    (folder / "job.json").write_text(json.dumps(job), encoding="utf-8")
    if stop:
        (folder / "stop").touch()
    return folder


def test_this_process_is_alive_and_its_start_time_is_known():
    started = process_started_at(os.getpid())
    assert started is not None and started <= datetime.now(UTC)
    assert alive(os.getpid(), datetime.now(UTC).isoformat())
    assert alive(os.getpid())
    assert not alive(None)


def test_a_reused_process_number_does_not_keep_the_job_running(tmp_path, monkeypatch):
    created = datetime(2026, 10, 16, 0, 53, tzinfo=UTC)
    monkeypatch.setattr(data_jobs, "_running", lambda pid: True)                  # 号码都有进程在用
    monkeypatch.setattr(data_jobs, "process_started_at", lambda pid: created + timedelta(days=6))  # 但都是后来启动的
    write_job(tmp_path, "20261016085344-stopped", created, stop=True)
    write_job(tmp_path, "20261016085345-gone", created)
    jobs = DataJobs(tmp_path, "config.yaml")
    status = {r["id"]: r["status"] for r in jobs.records()}
    assert status == {"20261016085344-stopped": "STOPPED", "20261016085345-gone": "INTERRUPTED"}
    assert jobs.active() is None                                                  # 可以启动新任务了


def test_a_job_whose_process_really_runs_stays_running(tmp_path, monkeypatch):
    created = datetime(2026, 10, 22, 6, 0, tzinfo=UTC)
    monkeypatch.setattr(data_jobs, "_running", lambda pid: True)
    monkeypatch.setattr(data_jobs, "process_started_at", lambda pid: created + timedelta(seconds=1))
    write_job(tmp_path, "20261022140000-live", created, stop=True)                # 点了停止，正在停
    record = DataJobs(tmp_path, "config.yaml").records()[0]
    assert record["status"] == "RUNNING" and record["stopping"] is True


def test_an_unreadable_process_is_someone_elses_on_windows(monkeypatch):
    monkeypatch.setattr(data_jobs, "_running", lambda pid: True)
    monkeypatch.setattr(data_jobs, "process_started_at", lambda pid: None)
    assert alive(123, "2026-10-16T00:53:45+00:00") is (os.name != "nt")
    assert alive(123) is True                                                     # 不给记录时间时照旧
