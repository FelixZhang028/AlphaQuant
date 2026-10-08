"""Validate and freeze jobs, then launch one detached worker per queued task."""

import json
import os
import subprocess
import sys
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime

import yaml

from quant_platform.api.common import ApiError, safe_wire
from quant_platform.application.data_jobs import alive, exclusive
from quant_platform.application.task_store import TERMINAL, TaskConflict, TaskStore


def lease_held(path):
    try:
        with exclusive(path):
            return False
    except RuntimeError:
        return True


@contextmanager
def launch_guard(path):
    lease = exclusive(path)
    try:
        lease.__enter__()
    except RuntimeError:
        # Another request is already launching this same task.
        yield False
        return
    try:
        yield True
    finally:
        lease.__exit__(None, None, None)


class TaskManager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.store = TaskStore(ctx.runtime_root / "tasks")

    def submit(self, body, key=None):
        inputs = body.input.model_dump(mode="json")
        with exclusive(self.store.root / ".submit.lock"):
            # Idempotent requests preserve the original snapshot even if defaults change.
            if key:
                with self.store.connect() as conn:
                    row = conn.execute(
                        "SELECT id,input,kind,retry_of FROM tasks WHERE idempotency_key=?", (key,)
                    ).fetchone()
                if row:
                    if (
                        json.loads(row["input"]) != inputs
                        or row["kind"] != body.kind
                        or row["retry_of"] is not None
                    ):
                        raise TaskConflict("同一幂等键不能提交不同参数")
                    self.reconcile(row["id"])
                    return self.store.get(row["id"])
            from quant_platform.api.backtests import build_request, experiment_base
            from quant_platform.api.workspace import factor_registry

            service = self.ctx.backtests()
            if body.kind == "backtest":
                if not body.input.confirmed:
                    raise ApiError(409, "confirmation_required", "请确认策略规则后再运行")
                build_request(service, body.input.request)
            elif body.kind in {"optimization", "walk_forward"}:
                experiment_base(service, body.input)
            elif body.kind == "factor_evaluation" and body.input.factor_name not in factor_registry(
                self.ctx
            ):
                raise ApiError(404, "factor_missing", "因子不存在")
            configs = deepcopy(service.configs)
            source_path = configs["app"].get("data", {}).get("source_config")
            if source_path and os.path.isfile(source_path):
                from quant_platform.core.config import load_yaml

                configs["data_sources"] = load_yaml(source_path)
            private = {
                "configs": configs,
                "config_path": str(self.ctx.config_path),
                "prior_path": str(self.ctx.prior_path),
                "cwd": str(os.getcwd()),
            }
            if body.kind == "ai_analysis":
                from quant_platform.api.ai_tasks import freeze_ai

                private["ai"] = freeze_ai(body.input, self.ctx)
            if body.kind in {"nl_strategy", "factor_combination", "xtick_query", "ai_chat"}:
                from quant_platform.api.advanced_tasks import freeze_advanced

                private["advanced"] = freeze_advanced(body.kind, body.input, self.ctx)
            item, _ = self.store.submit(body.kind, inputs, private, key=key)
        self.ensure_worker(item["id"])
        return self.store.get(item["id"])

    def frozen_config(self, identifier):
        item = self.store.get(identifier, private=True)
        configs = deepcopy(item["private"]["configs"])
        directory = self.store.directory(identifier)
        app = configs.pop("app")
        for section, value in configs.items():
            name = "source_config" if section == "data_sources" else "config"
            app_section = "data" if section == "data_sources" else section
            path = directory / f"{section}.yaml"
            path.write_text(yaml.safe_dump(value, allow_unicode=True), encoding="utf-8")
            app.setdefault(app_section, {})[name] = str(path)
        path = directory / "app.yaml"
        path.write_text(yaml.safe_dump(app, allow_unicode=True), encoding="utf-8")
        return path

    def ensure_worker(self, identifier):
        with launch_guard(self.store.directory(identifier) / ".launch.lock") as acquired:
            if not acquired:
                return
            item = self.store.get(identifier, private=True)
            if item["status"] != "QUEUED":
                return
            directory = self.store.directory(identifier)
            if lease_held(directory / ".worker.lock"):
                return
            if item["pid"] and alive(item["pid"]):
                age = (
                    datetime.now(UTC) - datetime.fromisoformat(item["updated_at"])
                ).total_seconds()
                if age < 30:
                    return
                self.store.finish(
                    identifier,
                    "FAILED",
                    {"code": "worker_start_failed", "message": "后台进程未能就绪，请重试任务"},
                )
                return
            flags = (
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            )
            try:
                self.frozen_config(identifier)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "quant_platform.api.task_worker",
                        "--root",
                        str(self.store.root),
                        "--id",
                        identifier,
                    ],
                    cwd=item["private"]["cwd"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                    **flags,
                )
                self.store.launched(identifier, process.pid)
            except OSError:
                self.store.finish(
                    identifier,
                    "FAILED",
                    {
                        "code": "worker_start_failed",
                        "message": "后台进程启动失败，请检查运行环境后重试",
                    },
                )

    def reconcile(self, identifier):
        item = self.store.get(identifier, private=True)
        if item["status"] in TERMINAL:
            return
        if lease_held(self.store.directory(identifier) / ".worker.lock"):
            return
        if item["status"] == "QUEUED":
            self.ensure_worker(identifier)
        else:
            self.repair_runs(identifier, item)
            self.store.finish(
                identifier,
                "INTERRUPTED",
                {
                    "code": "worker_interrupted",
                    "message": "后台进程已中断；已有结果保留，可手动重试",
                },
            )

    def repair_runs(self, identifier, item):
        import re
        from pathlib import Path

        from quant_platform.backtest.run_store import BacktestRunStore

        runtime = item["private"]["configs"]["app"]["app"]["runtime_dir"]
        runs = BacktestRunStore(Path(runtime) / "runs")
        for event in self.store.events(identifier, limit=100000):
            stage = event.get("stage", "")
            if not stage.startswith("run_created:"):
                continue
            run_id = stage.split(":", 1)[1]
            if not re.fullmatch(r"[a-f0-9-]{36}", run_id):
                continue
            path = runs.root / run_id / "run.json"
            if path.is_file():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if raw.get("status") in {"CREATED", "RUNNING"}:
                    runs.fail(run_id, RuntimeError("后台任务中断，原始运行已保留"))

    def recover(self):
        for identifier in self.store.pending():
            self.reconcile(identifier)

    def retry(self, identifier, key=None):
        self.reconcile(identifier)
        item = self.store.get(identifier, private=True)
        if item["status"] not in {"FAILED", "PARTIAL", "CANCELLED", "INTERRUPTED"}:
            raise TaskConflict("仅失败、部分完成、取消或中断的任务可以重试")
        # Retry the exact stored submission/snapshot and keep the original task auditable.
        with exclusive(self.store.root / ".submit.lock"):
            result, _ = self.store.submit(
                item["kind"], item["input"], item["private"], key=key, retry_of=identifier
            )
        self.ensure_worker(result["id"])
        return safe_wire(self.store.get(result["id"]))
