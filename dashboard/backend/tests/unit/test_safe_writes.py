"""Data files are swapped in whole, data jobs outlive the launcher, and Jev's real version is shown."""
import json
import os
import subprocess
import time
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_platform.application import data_jobs
from quant_platform.ai_research.decisions import model_name
from quant_platform.core import files
from quant_platform.core.files import write_json_atomic
from quant_platform.data.repositories import parquet_repository
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository, write_parquet_atomic
from quant_platform.jev.client import JevClient, choice_question


def bars(days, close):
    return pd.DataFrame({"symbol": "000001.SZ", "trade_date": pd.to_datetime(days), "raw_open": close, "raw_close": close})


def test_a_write_stopped_halfway_leaves_the_old_file_whole(tmp_path, monkeypatch):
    repo = ParquetMarketDataRepository(tmp_path)
    repo.save_table("daily_bars", bars(["2026-10-08", "2026-10-09"], 10.0))
    before = repo.get_daily_bars()

    def killed_halfway(self, path, **options):
        with open(path, "wb") as handle:
            handle.write(b"PAR1 only part of a parquet file")
        raise KeyboardInterrupt("进程在写文件时被结束")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", killed_halfway)
    with pytest.raises(KeyboardInterrupt):
        repo.save_table("daily_bars", bars(["2026-10-12"], 11.0))
    monkeypatch.undo()
    pd.testing.assert_frame_equal(repo.get_daily_bars(), before)          # 原来的文件完好
    assert not list(tmp_path.rglob("*.tmp"))                               # 也没留下临时文件


def test_a_writer_never_shows_readers_a_temporary_file(tmp_path, monkeypatch):
    repo = ParquetMarketDataRepository(tmp_path)
    repo.save_table("daily_bars", bars(["2026-10-08"], 10.0))
    seen = []
    original = pd.DataFrame.to_parquet

    def slow(self, path, **options):
        original(self, path, **options)
        # 新文件已经写好、还没换上：这时读到的是旧的完整数据，临时文件不算行情文件。
        seen.append((len(repo.get_daily_bars()), sorted(p.name for p in tmp_path.rglob("*.parquet"))))

    monkeypatch.setattr(pd.DataFrame, "to_parquet", slow)
    repo.save_table("daily_bars", bars(["2026-10-09"], 11.0))
    assert seen == [(1, ["data.parquet"])]
    assert len(repo.get_daily_bars()) == 2


def test_a_file_being_read_on_windows_is_replaced_once_the_reader_lets_go(tmp_path, monkeypatch):
    path = tmp_path / "security_master.parquet"
    write_parquet_atomic(pd.DataFrame({"symbol": ["A"]}), path)
    attempts = []
    original = os.replace

    def busy_twice(source, target):
        attempts.append(1)
        if len(attempts) <= 2:
            raise PermissionError("另一个程序正在使用此文件")
        original(source, target)

    monkeypatch.setattr(files.os, "replace", busy_twice)
    write_parquet_atomic(pd.DataFrame({"symbol": ["A", "B"]}), path)
    assert len(attempts) == 3 and pd.read_parquet(path)["symbol"].tolist() == ["A", "B"]


def test_a_job_file_being_read_is_replaced_once_the_reader_lets_go(tmp_path, monkeypatch):
    # 2026-10-20：后台每几秒读一次 progress.json，下载任务正好在这时替换它，Windows 报“拒绝访问”，整个任务失败。
    path = tmp_path / "progress.json"
    data_jobs.write_json(path, {"done": 1})
    attempts = []
    original = os.replace

    def busy_twice(source, target):
        attempts.append(1)
        if len(attempts) <= 2:
            raise PermissionError("[WinError 5] 拒绝访问。")
        original(source, target)

    monkeypatch.setattr(files.os, "replace", busy_twice)
    data_jobs.write_json(path, {"done": 2})
    assert len(attempts) == 3 and json.loads(path.read_text(encoding="utf-8")) == {"done": 2}
    assert not list(tmp_path.glob("*.tmp"))


def test_a_file_held_too_long_fails_without_leaving_a_temporary(tmp_path, monkeypatch):
    def always_busy(source, target):
        raise PermissionError("拒绝访问")

    monkeypatch.setattr(files.os, "replace", always_busy)
    monkeypatch.setattr(files, "REPLACE_WAIT_SECONDS", 0.1)
    with pytest.raises(PermissionError):
        write_json_atomic(tmp_path / "state.json", {"x": 1})
    assert not list(tmp_path.glob("*.tmp")) and not (tmp_path / "state.json").exists()


def test_a_download_keeps_going_when_its_progress_cannot_be_saved(tmp_path, monkeypatch):
    def download(start, end, symbols=None, progress=None):
        for done in range(3):
            progress("quarterly_fundamentals", done, 3)
        return {"failed": {}, "reports": 3}

    service = SimpleNamespace(app={"app": {"runtime_dir": str(tmp_path)}}, backfill_fundamentals=download)
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: service)
    original = data_jobs.write_json

    def progress_locked(path, value):
        if path.name == "progress.json":
            raise PermissionError("[WinError 5] 拒绝访问。")
        original(path, value)

    monkeypatch.setattr(data_jobs, "write_json", progress_locked)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2026-01-01", "end_date": "2026-10-20", "datasets": ["fundamentals"]}
    assert data_jobs.attempt(folder, job) == 0
    assert data_jobs.read_json(folder / "result.json")["quarterly_fundamentals"]["reports"] == 3


def test_temporaries_left_by_a_killed_write_are_cleaned_up_later(tmp_path):
    path = tmp_path / "security_master.parquet"
    stale, fresh = tmp_path / ".security_master.parquet.old.tmp", tmp_path / ".security_master.parquet.new.tmp"
    stale.write_bytes(b"x")
    fresh.write_bytes(b"x")
    long_ago = time.time() - 2 * parquet_repository._STALE_TEMPORARY_SECONDS
    os.utime(stale, (long_ago, long_ago))
    write_parquet_atomic(pd.DataFrame({"symbol": ["A"]}), path)
    assert not stale.exists() and fresh.exists()                         # 正在写的不动


@pytest.mark.skipif(os.name != "nt", reason="Windows job objects")
def test_a_data_job_falls_back_when_its_job_does_not_allow_breaking_away(monkeypatch):
    calls = []

    def popen(command, creationflags=0, **options):
        calls.append(creationflags)
        if creationflags & subprocess.CREATE_BREAKAWAY_FROM_JOB:
            raise PermissionError("拒绝访问")
        return "started"

    monkeypatch.setattr(data_jobs.subprocess, "Popen", popen)
    assert data_jobs.launch_detached(["python"]) == "started"
    assert calls == [subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB, subprocess.CREATE_NO_WINDOW]


def test_the_version_that_answered_is_shown_not_the_alias(monkeypatch):
    client = JevClient("key", model="jev-latest")
    assert model_name(client) == "jev-latest" and client.served_model is None
    answer = {"type": "choice", "choice": "是", "probabilities": {"是": 0.6, "否": 0.4}, "confidence": 0.7}
    monkeypatch.setattr(client, "_post", lambda payload: {"model": "jev-1.13.0", "answers": {"q": answer}})
    client.ask({}, {"q": choice_question("问题", {"是": "", "否": ""})})
    assert client.served_model == "jev-1.13.0" and model_name(client) == "jev-1.13.0"
    assert model_name(JevClient("key", model="typesafe/jev-1.13")) == "jev-1.13"
