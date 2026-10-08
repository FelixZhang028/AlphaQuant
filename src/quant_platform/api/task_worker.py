"""One detached, serially scheduled task; independent of the API process lifetime."""

import argparse
import time
from pathlib import Path

from quant_platform.api.common import ApiError, safe_wire
from quant_platform.api.dependencies import ApiContext
from quant_platform.application.data_jobs import exclusive
from quant_platform.application.task_store import TERMINAL, TaskStore
from quant_platform.core.diagnostics import redact_text
from quant_platform.core.exceptions import OperationCancelled


class TaskProgress:
    def __init__(self, store, identifier):
        self.store, self.identifier = store, identifier
        self.last_time, self.last_stage = 0.0, None

    def __call__(self, stage, completed, total):
        if self.store.get(self.identifier)["cancel_requested"]:
            raise OperationCancelled("任务已在安全边界取消")
        current = time.monotonic()
        if current - self.last_time >= 0.5 or stage != self.last_stage or completed == total:
            self.store.progress(self.identifier, stage, completed, total)
            self.last_time, self.last_stage = current, stage


def dispatch(kind, inputs, ctx, private=None, store=None, identifier=None):
    if kind in {"nl_strategy", "factor_combination", "xtick_query", "ai_chat"}:
        from quant_platform.api.advanced_tasks import execute_advanced

        return safe_wire(execute_advanced(kind, inputs, ctx, private))
    from quant_platform.api import backtests, catalog, data
    from quant_platform.api.schemas import (
        FactorEvaluationInput,
        OptimizationInput,
        RunInput,
        UpdateInput,
        WalkForwardInput,
    )

    if kind == "ai_analysis":
        from quant_platform.api.ai_tasks import execute_ai
        from quant_platform.api.task_schemas import AIInput

        return execute_ai(AIInput.model_validate(inputs), ctx, private["ai"], store, identifier)
    operations = {
        "backtest": (RunInput, backtests.run),
        "optimization": (OptimizationInput, backtests.optimize),
        "walk_forward": (WalkForwardInput, backtests.walk_forward),
        "factor_evaluation": (FactorEvaluationInput, catalog.evaluate),
        "data_update": (UpdateInput, data.update),
    }
    schema, operation = operations[kind]
    ctx.progress("execute", 0, 1)
    result = safe_wire(operation(schema.model_validate(inputs), ctx))
    # No progress percentage is invented for services without internal callbacks.
    return result


def outcome(kind, result):
    rows = []
    if kind == "optimization":
        rows = result["experiments"]["rows"]
    elif kind == "walk_forward":
        rows = result["windows"]["rows"]
    elif kind == "data_update":
        rows = result["results"]
    if rows:
        succeeded = sum(str(row.get("status", "")).upper() == "SUCCESS" for row in rows)
        if succeeded == 0:
            return "FAILED"
        if succeeded != len(rows):
            return "PARTIAL"
    return "SUCCESS"


def work(root, identifier):
    store = TaskStore(root)
    with exclusive(store.directory(identifier) / ".worker.lock"):
        item = store.get(identifier, private=True)
        ctx = ApiContext(
            store.directory(identifier) / "app.yaml", Path(item["private"]["prior_path"])
        )
        ctx.progress = TaskProgress(store, identifier)
        try:
            while True:
                current = store.get(identifier)
                if current["status"] in TERMINAL:
                    return
                with store.connect() as conn:
                    first = conn.execute(
                        "SELECT id FROM tasks WHERE status='QUEUED' ORDER BY created_at LIMIT 1"
                    ).fetchone()
                if first is not None and first[0] != identifier:
                    time.sleep(0.2)
                    continue
                try:
                    with ctx.mutation():
                        if not store.claim(identifier):
                            return
                        ctx.progress("starting", 0, 1)
                        result = dispatch(
                            item["kind"], item["input"], ctx, item["private"], store, identifier
                        )
                        status = (
                            "CANCELLED"
                            if store.get(identifier)["cancel_requested"]
                            else outcome(item["kind"], result)
                        )
                        error = (
                            {
                                "code": "all_items_failed",
                                "message": "全部子操作失败，请查看结果明细",
                            }
                            if status == "FAILED"
                            else None
                        )
                        store.finish(identifier, status, error, result)
                        return
                except ApiError as exc:
                    if exc.code != "operation_busy" or store.get(identifier)["status"] != "QUEUED":
                        raise
                    time.sleep(0.2)
        except OperationCancelled:
            store.finish(identifier, "CANCELLED")
        except ApiError as exc:
            store.finish(
                identifier,
                "FAILED",
                {"code": exc.code, "message": exc.message, "details": safe_wire(exc.details)},
            )
        except Exception as exc:
            # Avoid arbitrary remote response bodies or credentials in public logs.
            from quant_platform.core.exceptions import ConfigurationError, PluginError

            message = (
                redact_text(exc)[:1000]
                if isinstance(exc, (ValueError, ConfigurationError, PluginError))
                else "后台任务失败，请检查数据或运行环境后重试"
            )
            store.finish(identifier, "FAILED", {"code": type(exc).__name__, "message": message})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    work(args.root, args.id)


if __name__ == "__main__":
    main()
