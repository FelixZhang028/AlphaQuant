import os
import subprocess
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from quant_platform.application import data_jobs as jobs_module
from quant_platform.application.data_jobs import DataJobs, exclusive, read_json, write_json


def test_launch_duplicate_stop_and_interrupted(tmp_path, monkeypatch):
    calls = []

    def launch(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(pid=os.getpid())

    monkeypatch.setattr(subprocess, "Popen", launch)
    jobs = DataJobs(tmp_path)
    job = jobs.start(date(2020, 1, 1), date(2020, 2, 1), ["bars"])
    assert jobs.active()["id"] == job["id"]
    assert calls[0][0][0] == sys.executable
    assert calls[0][1]["stdin"] == subprocess.DEVNULL
    with pytest.raises(RuntimeError):
        jobs.start(date(2020, 1, 1), date(2020, 2, 1), ["bars"])
    jobs.stop(job["id"])
    assert jobs.active()["stopping"]
    monkeypatch.setattr(jobs_module, "alive", lambda pid: False)
    assert jobs.records()[0]["status"] == "INTERRUPTED"
    assert not jobs.active()


def test_lock_blocks_other_process_and_releases(tmp_path):
    path = tmp_path / "writer.lock"
    command = [
        sys.executable,
        "-c",
        "from quant_platform.application.data_jobs import exclusive; "
        "import sys; "
        "\nwith exclusive(sys.argv[1]): print('acquired')",
        str(path),
    ]
    with exclusive(path):
        blocked = subprocess.run(command, capture_output=True, timeout=10)
        assert blocked.returncode != 0
    assert subprocess.run(command, capture_output=True, timeout=10).returncode == 0


@pytest.mark.parametrize(
    "codes, expected",
    [([86, 0], "SUCCESS"), ([2], "PARTIAL"), ([130], "STOPPED"), ([1] * 21, "FAILED")],
)
def test_supervisor_retry_and_terminal_states(tmp_path, monkeypatch, codes, expected):
    folder = tmp_path / "task"
    folder.mkdir()
    write_json(folder / "job.json", {"cwd": str(tmp_path), "pid": os.getpid()})
    attempts = iter(codes)
    calls = []

    def launch(command, **kwargs):
        calls.append(command)
        code = next(attempts)
        return SimpleNamespace(pid=os.getpid(), wait=lambda: code)

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(jobs_module.time, "sleep", lambda seconds: None)
    jobs_module.supervise(folder)
    result = read_json(folder / "job.json")
    assert result["status"] == expected
    assert len(calls) == len(codes)
    assert calls[0][3] == jobs_module.MODULE


def test_stop_before_attempt_never_contacts_provider(tmp_path):
    (tmp_path / "stop").touch()
    # Empty job would fail if the worker attempted to construct a service.
    with pytest.raises(SystemExit) as exc:
        jobs_module.attempt(tmp_path, {})
    assert exc.value.code == 130


def test_worker_module_accepts_stop_without_network(tmp_path):
    (tmp_path / "stop").touch()
    write_json(tmp_path / "job.json", {})
    result = subprocess.run(
        [sys.executable, "-m", jobs_module.MODULE, str(tmp_path), "--attempt"],
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 130
    assert read_json(tmp_path / "progress.json")["stage"] == "security_master"


def test_panel_navigation_and_start(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/app.yaml").write_text(
        "app:\n  runtime_dir: runtime\ndata:\n  repository: runtime/market\n"
        "universe:\n  config: configs/universe.yaml\nbacktest:\n  benchmark: 000300.SH\n",
        encoding="utf-8",
    )
    (tmp_path / "configs/universe.yaml").write_text(
        "universe:\n  symbols: ['000001.SZ']\n", encoding="utf-8"
    )
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/1_data_management.py"
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(page), default_timeout=20).run()
    assert not app.exception
    assert app.title[0].value == "数据更新"
    app.session_state["data_update_section"] = "全市场回填"
    app.run()
    assert not app.exception
    calls = []
    monkeypatch.setattr(DataJobs, "start", lambda self, *args: calls.append(args))
    next(b for b in app.button if b.label == "启动回填").click().run()
    assert not app.exception
    assert calls[0][0] == date(2015, 1, 1)
    assert calls[0][2] == ["bars", "actions", "derived"]
    app.session_state["data_update_section"] = "任务记录"
    app.run()
    assert not app.exception
    assert any("暂无后台回填任务" in item.value for item in app.info)


def test_invalid_dates_and_empty_datasets_do_not_launch(tmp_path):
    jobs = DataJobs(tmp_path)
    with pytest.raises(ValueError):
        jobs.start(date(2021, 1, 1), date(2020, 1, 1), ["bars"])
    with pytest.raises(ValueError):
        jobs.start(date(2020, 1, 1), date(2020, 1, 1), [])
    assert jobs.records() == []
