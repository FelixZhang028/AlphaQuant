"""Detached workers, durable state, safe cancellation and immutable submissions."""

import json
import os
import time
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_api import completed as completed
from test_api import environment as environment

from quant_platform.api.main import create_app
from quant_platform.api.task_worker import work
from quant_platform.application.task_store import TERMINAL

PREFIX = "/api/v1/tasks"


def wait_for(client, identifier, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"{PREFIX}/{identifier}")
        assert response.status_code == 200, response.text
        if response.json()["status"] in TERMINAL:
            return response.json()
        time.sleep(0.1)
    pytest.fail(f"Task {identifier} did not complete: {response.text}")


def submission(client):
    request = client.get("/api/v1/backtests/defaults").json()
    return {"kind": "backtest", "input": {"request": request, "confirmed": True}}


def stored_job(environment, *, inputs=None):
    root, app, client, service = environment
    manager = app.state.context.tasks
    private = {
        "configs": deepcopy(service.configs),
        "config_path": str(service.app_config_path),
        "prior_path": str(root / "prior.json"),
        "cwd": os.getcwd(),
    }
    body = submission(client)
    item, _ = manager.store.submit("backtest", inputs or body["input"], private)
    manager.frozen_config(item["id"])
    return manager, item


def test_submission_returns_202_and_detached_result_matches_engine(
    environment, completed, monkeypatch
):
    root, app, client, service = environment
    _, direct = completed
    body = submission(client)
    # A parent-process patch cannot affect a detached Python worker.
    monkeypatch.setattr(type(service), "run", lambda *args: pytest.fail("HTTP thread ran backtest"))
    response = client.post(PREFIX, json=body, headers={"Idempotency-Key": "backtest-once"})
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    assert response.headers["location"] == f"{PREFIX}/{identifier}"
    again = client.post(PREFIX, json=body, headers={"Idempotency-Key": "backtest-once"})
    assert again.status_code == 202 and again.json()["id"] == identifier
    private = app.state.context.tasks.store.get(identifier, private=True)
    assert private["pid"] and private["pid"] != os.getpid()
    item = wait_for(client, identifier)
    assert item["status"] == "SUCCESS", item
    result = client.get(f"{PREFIX}/{identifier}/result").json()
    assert result["summary"]["cumulative_return"] == pytest.approx(
        direct.result.summary["cumulative_return"]
    )
    assert result["summary"]["sharpe"] == pytest.approx(direct.result.summary["sharpe"])
    from quant_platform.api.common import safe_wire

    nav = client.get(f"/api/v1/runs/{result['run_id']}/tables/nav?limit=5000").json()
    assert nav["rows"] == safe_wire(direct.result.nav)["rows"]
    assert item["progress"] == {"stage": "finished", "completed": 1, "total": 1}
    assert "private" not in item and "input" not in item and "pid" not in item
    events = client.get(f"{PREFIX}/{identifier}/events").json()
    assert any(row["stage"] == "backtest_days" for row in events["items"])
    assert (
        client.get(f"{PREFIX}/{identifier}/events?after={events['next_after']}").json()["items"]
        == []
    )
    changed = deepcopy(body)
    changed["input"]["request"]["top_n"] = 1
    assert (
        client.post(PREFIX, json=changed, headers={"Idempotency-Key": "backtest-once"}).status_code
        == 409
    )
    # Same persistent database, brand-new application object and request session.
    with TestClient(
        create_app(service.app_config_path, prior_path=root / "prior.json")
    ) as refreshed:
        assert refreshed.get(f"{PREFIX}/{identifier}").json()["status"] == "SUCCESS"
        assert refreshed.get(f"{PREFIX}/{identifier}/result").json() == result


def test_queue_survives_api_close_and_freezes_execution_config(environment):
    root, app, client, service = environment
    body = submission(client)
    execution = service.app_config_path.parent / "execution.yaml"
    original = execution.read_text(encoding="utf-8")
    import yaml

    with app.state.context.mutation():
        temporary_app = create_app(service.app_config_path, prior_path=root / "prior.json")
        with TestClient(temporary_app) as temporary_client:
            response = temporary_client.post(PREFIX, json=body)
            assert response.status_code == 202, response.text
            identifier = response.json()["id"]
            assert temporary_client.get(f"{PREFIX}/{identifier}").json()["status"] == "QUEUED"
        modified = yaml.safe_load(original)
        modified["execution"]["slippage_rate"] = 0.8
        execution.write_text(yaml.safe_dump(modified), encoding="utf-8")
    try:
        item = wait_for(client, identifier)
        assert item["status"] == "SUCCESS", item
        result = client.get(f"{PREFIX}/{identifier}/result").json()
        saved = yaml.safe_load(
            (service.runs_root / result["run_id"] / "config.snapshot.yaml").read_text(
                encoding="utf-8"
            )
        )
        assert saved["execution"]["execution"]["slippage_rate"] == 0
    finally:
        execution.write_text(original, encoding="utf-8")


def test_queued_cancel_and_retry_preserve_original(environment):
    _, app, client, _ = environment
    with app.state.context.mutation():
        response = client.post(PREFIX, json=submission(client))
        assert response.status_code == 202, response.text
        identifier = response.json()["id"]
        cancelled = client.post(f"{PREFIX}/{identifier}/cancel")
        assert cancelled.json()["status"] == "CANCELLED"
        assert client.get(f"{PREFIX}/{identifier}/result").status_code == 409
        retried = client.post(
            f"{PREFIX}/{identifier}/retry", headers={"Idempotency-Key": "retry-once"}
        )
        assert retried.status_code == 202, retried.text
        new_id = retried.json()["id"]
        assert new_id != identifier and retried.json()["retry_of"] == identifier
        again = client.post(
            f"{PREFIX}/{identifier}/retry", headers={"Idempotency-Key": "retry-once"}
        )
        assert again.json()["id"] == new_id
    assert wait_for(client, new_id)["status"] == "SUCCESS"
    assert client.get(f"{PREFIX}/{identifier}").json()["status"] == "CANCELLED"


def test_failed_check_is_persisted_and_retry_creates_new_attempt(environment):
    _, _, client, _ = environment
    body = submission(client)
    body["input"]["request"].update(start_date="2070-01-01", end_date="2070-02-01")
    response = client.post(PREFIX, json=body)
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    failed = wait_for(client, identifier)
    assert failed["status"] == "FAILED" and failed["error"]["code"] == "data_not_ready"
    retried = client.post(f"{PREFIX}/{identifier}/retry")
    assert retried.status_code == 202
    assert wait_for(client, retried.json()["id"])["status"] == "FAILED"


def test_worker_crash_marks_interrupted_and_preserves_run(environment):
    _, _, client, service = environment
    manager, item = stored_job(environment)
    identifier = item["id"]
    assert manager.store.claim(identifier)
    run_id = str(uuid4())
    service.run_store.start(run_id, service._config_snapshot(service.default_request()))
    service.run_store.mark_running(run_id)
    manager.store.progress(identifier, "run_created:" + run_id, 0, 1)
    manager.reconcile(identifier)
    state = client.get(f"{PREFIX}/{identifier}").json()
    assert state["status"] == "INTERRUPTED"
    records = {record.run_id: record for record in service.run_store.list_records()}
    assert records[run_id].status == "FAILED"
    assert (service.runs_root / run_id / "run.json").is_file()


def test_running_cancel_at_safe_boundary_and_partial_results(environment, monkeypatch):
    import quant_platform.api.task_worker as worker

    manager, item = stored_job(environment)

    def cancel_dispatch(kind, inputs, ctx, private, store, identifier):
        store.cancel(identifier)
        ctx.progress("safe_boundary", 0, 1)

    monkeypatch.setattr(worker, "dispatch", cancel_dispatch)
    work(manager.store.root, item["id"])
    assert manager.store.get(item["id"])["status"] == "CANCELLED"
    manager, item = stored_job(environment)
    monkeypatch.setattr(
        worker,
        "dispatch",
        lambda *args: {
            "experiments": {
                "rows": [
                    {"status": "SUCCESS"},
                    {"status": "FAILED", "error": "api_key=test-secret"},
                ]
            }
        },
    )
    with manager.store.connect() as conn:
        conn.execute("UPDATE tasks SET kind='optimization' WHERE id=?", (item["id"],))
    work(manager.store.root, item["id"])
    assert manager.store.get(item["id"])["status"] == "PARTIAL"
    assert "test-secret" not in json.dumps(manager.store.result(item["id"]))
    # Services without internal callbacks finish their current atomic operation,
    # then honor cancellation and retain the already produced result.
    manager, item = stored_job(environment)

    def finish_after_cancel(*args):
        manager.store.cancel(item["id"])
        return {"completed_output": True}

    monkeypatch.setattr(worker, "dispatch", finish_after_cancel)
    work(manager.store.root, item["id"])
    assert manager.store.get(item["id"])["status"] == "CANCELLED"
    assert manager.store.result(item["id"])["completed_output"]


def test_concurrent_launch_guard_preserves_single_worker(environment):
    from quant_platform.application.data_jobs import exclusive

    manager, item = stored_job(environment)
    with exclusive(manager.store.directory(item["id"]) / ".launch.lock"):
        manager.ensure_worker(item["id"])
        assert manager.store.get(item["id"], private=True)["pid"] is None
    manager.ensure_worker(item["id"])
    assert wait_for(environment[2], item["id"])["status"] == "SUCCESS"


@pytest.mark.parametrize(
    "kind,inputs",
    [
        (
            "factor_evaluation",
            {"factor_name": "momentum_20", "start_date": "2023-01-03", "end_date": "2023-04-28"},
        ),
        ("optimization", {"parameter_grid": {"short_window": [15, 20]}}),
        (
            "walk_forward",
            {
                "parameter_grid": {"short_window": [20]},
                "start_date": "2022-07-01",
                "end_date": "2023-12-29",
                "training_months": 3,
                "test_months": 1,
                "max_windows": 1,
            },
        ),
        (
            "ai_analysis",
            {
                "symbol": "000001",
                "trade_date": "2023-04-28",
                "provider": "mock",
                "use_cache": False,
            },
        ),
    ],
)
def test_real_detached_research_operations(environment, completed, kind, inputs):
    _, _, client, service = environment
    run_id, _ = completed
    inputs = dict(inputs)
    if kind in {"optimization", "walk_forward"}:
        inputs["baseline_run_id"] = run_id
    response = client.post(PREFIX, json={"kind": kind, "input": inputs})
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    item = wait_for(client, identifier)
    assert item["status"] == "SUCCESS", item
    result = client.get(f"{PREFIX}/{identifier}/result").json()
    if kind == "optimization":
        nav = service.runs_root / result["experiments"]["rows"][0]["run_id"] / "nav.parquet"
        original = nav.read_bytes()
        try:
            nav.unlink()
            reloaded = client.get(f"{PREFIX}/{identifier}/result").json()
            assert all(row["dsr"] is None for row in reloaded["experiments"]["rows"])
            assert all(item["status"] == "unavailable" for item in reloaded["selection_bias"])
        finally:
            nav.write_bytes(original)
    if kind == "ai_analysis":
        assert result["state"] is not None and result["decision"]
        assert "runner" not in result
        assert any(
            event["stage"] == "ai_node"
            for event in client.get(f"{PREFIX}/{identifier}/events").json()["items"]
        )


def test_invalid_tasks_and_start_failure(environment, monkeypatch):
    import quant_platform.api.background as background

    _, app, client, _ = environment
    assert client.get(PREFIX + "/../secret").status_code == 404
    assert client.get(PREFIX + "/unknown").status_code == 404
    body = submission(client)
    body["input"]["confirmed"] = False
    assert client.post(PREFIX, json=body).status_code == 409
    assert client.post(PREFIX, json={"kind": "execute_shell", "input": {}}).status_code == 422

    def fail(*args, **kwargs):
        raise OSError("launch failed api_key=test-secret")

    monkeypatch.setattr(background.subprocess, "Popen", fail)
    response = client.post(PREFIX, json=submission(client))
    assert response.status_code == 202
    item = app.state.context.tasks.store.get(response.json()["id"])
    assert item["status"] == "FAILED" and item["error"]["code"] == "worker_start_failed"
    assert "test-secret" not in json.dumps(item)


@pytest.mark.parametrize("statuses,expected_status", [(["SUCCESS", "FAILED"], "PARTIAL"), (["FAILED", "FAILED"], "FAILED"), (["SUCCESS", "SUCCESS"], "SUCCESS")])
def test_data_update_adapter_retains_partial_results(environment, monkeypatch, statuses, expected_status):
    from quant_platform.api.background import TaskManager
    from quant_platform.application.data_jobs import DataJobs
    from quant_platform.application.data_service import DataCenterService, DataUpdateResult

    _, app, client, _ = environment
    monkeypatch.setattr(TaskManager, "ensure_worker", lambda *args: None)
    monkeypatch.setattr(DataJobs, "active", lambda self: None)
    monkeypatch.setattr(
        DataCenterService,
        "update_all",
        lambda *args, **kwargs: [
            DataUpdateResult("daily_bars", "ok", statuses[0], 20, "完成"),
            DataUpdateResult(
                "corporate_actions", "failed", statuses[1], 0, "失败", "api_key=test-secret"
            ),
        ],
    )
    response = client.post(
        PREFIX,
        json={
            "kind": "data_update",
            "input": {
                "start_date": "2023-01-03",
                "end_date": "2023-04-28",
                "datasets": ["daily_bars", "corporate_actions"],
            },
        },
    )
    assert response.status_code == 202, response.text
    identifier = response.json()["id"]
    manager = app.state.context.tasks
    manager.frozen_config(identifier)
    work(manager.store.root, identifier)
    assert client.get(f"{PREFIX}/{identifier}").json()["status"] == expected_status
    result = client.get(f"{PREFIX}/{identifier}/result").json()
    assert len(result["results"]) == 2 and "test-secret" not in json.dumps(result)


def test_detached_task_survives_real_api_process_restart(environment):
    import socket
    import subprocess
    import sys

    import httpx

    _, app, client, service = environment
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    base = f"http://127.0.0.1:{port}"
    processes = []

    def server():
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "quant_platform.api.cli",
                "--port",
                str(port),
                "--config",
                str(service.app_config_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            **flags,
        )
        processes.append(process)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            assert process.poll() is None, "API server exited during startup"
            try:
                if httpx.get(base + "/api/v1/health", timeout=0.5).status_code == 200:
                    return process
            except httpx.TransportError:
                pass
            time.sleep(0.1)
        pytest.fail("API server did not start")

    try:
        process = server()
        with app.state.context.mutation():
            response = httpx.post(base + PREFIX, json=submission(client), timeout=10)
            assert response.status_code == 202, response.text
            identifier = response.json()["id"]
            assert response.json()["status"] == "QUEUED"
            process.terminate()
            process.wait(timeout=10)
        # Only the detached worker is alive now; no HTTP process can execute this job.
        store = app.state.context.tasks.store
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline and store.get(identifier)["status"] not in TERMINAL:
            time.sleep(0.1)
        assert store.get(identifier)["status"] == "SUCCESS"
        server()
        assert httpx.get(base + PREFIX + "/" + identifier).json()["status"] == "SUCCESS"
        assert httpx.get(base + PREFIX + "/" + identifier + "/result").json()["run_id"]
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
