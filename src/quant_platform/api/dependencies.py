"""Per-request services and process-wide write exclusion."""

from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from fastapi import Request

from quant_platform.api.common import ApiError
from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.data_jobs import exclusive
from quant_platform.application.data_service import DataCenterService
from quant_platform.core.config import load_app_config, require_mapping


@dataclass
class ApiContext:
    config_path: Path
    prior_path: Path
    write_lock: RLock = field(default_factory=RLock)
    progress: object = None
    _depth: int = field(default=0, init=False)
    _tasks: object = field(default=None, init=False)

    @property
    def runtime_root(self):
        config = load_app_config(self.config_path)
        return Path(str(require_mapping(config, "app")["runtime_dir"]))

    @property
    def tasks(self):
        if self._tasks is None:
            from quant_platform.api.background import TaskManager

            self._tasks = TaskManager(self)
        return self._tasks

    def backtests(self) -> BacktestService:
        # Reload configuration/strategies after edits made in either interface.
        return BacktestService(self.config_path, progress=self.progress)

    def data(self) -> DataCenterService:
        return DataCenterService(self.config_path)

    @contextmanager
    def mutation(self):
        if not self.write_lock.acquire(blocking=False):
            raise ApiError(409, "operation_busy", "已有写入或计算操作正在执行，请完成后重试")
        try:
            if self._depth:
                self._depth += 1
                try:
                    yield
                finally:
                    self._depth -= 1
            else:
                try:
                    lease = exclusive(self.runtime_root / ".api-mutation.lock")
                    lease.__enter__()
                except RuntimeError as exc:
                    raise ApiError(409, "operation_busy", "后台任务正在执行，请完成后重试") from exc
                self._depth = 1
                try:
                    yield
                finally:
                    self._depth = 0
                    lease.__exit__(None, None, None)
        finally:
            self.write_lock.release()


def context(request: Request) -> ApiContext:
    return request.app.state.context
