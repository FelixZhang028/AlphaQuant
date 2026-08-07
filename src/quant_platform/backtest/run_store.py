"""Lifecycle metadata and discovery for persisted backtest runs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


class RunStatus(StrEnum):
    """Lifecycle states visible to every user interface."""

    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class RunRecord:
    """Compact metadata for one persisted backtest run."""

    run_id: str
    status: RunStatus
    created_at: str
    updated_at: str
    strategy_plugin: str
    strategy_id: str
    start_date: str
    end_date: str
    error: str | None
    path: Path
    run_kind: str = "single"
    parent_experiment_id: str | None = None
    baseline_run_id: str | None = None


class BacktestRunStore:
    """Create lifecycle records and read old and new run directories."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def start(self, run_id: str, snapshot: dict[str, Any]) -> Path:
        """Reserve a run directory before execution so failures are auditable."""

        directory = self.root / run_id
        directory.mkdir(parents=True, exist_ok=False)
        now = datetime.now(UTC).isoformat()
        strategy = _mapping(_mapping(snapshot.get("strategy")).get("strategy"))
        app = _mapping(_mapping(snapshot.get("app")).get("backtest"))
        self._write(
            directory,
            {
                "run_id": run_id,
                "status": RunStatus.CREATED.value,
                "created_at": now,
                "updated_at": now,
                "strategy_plugin": str(strategy.get("plugin", "")),
                "strategy_id": str(strategy.get("id", "")),
                "start_date": str(app.get("start_date", "")),
                "end_date": str(app.get("end_date", "")),
                "run_kind": str(app.get("run_kind", "single")),
                "parent_experiment_id": app.get("parent_experiment_id"),
                "baseline_run_id": app.get("baseline_run_id"),
                "error": None,
            },
        )
        return directory

    def mark_running(self, run_id: str) -> None:
        """Mark a reserved run as executing."""

        self._update(run_id, RunStatus.RUNNING)

    def complete(self, run_id: str) -> None:
        """Mark a run successful after all artifacts have been saved."""

        self._update(run_id, RunStatus.SUCCESS)

    def fail(self, run_id: str, error: Exception) -> None:
        """Preserve a bounded error for a failed run."""

        message = f"{type(error).__name__}: {error}"[:2000]
        self._update(run_id, RunStatus.FAILED, message)

    def list_records(self, *, successful_only: bool = False) -> list[RunRecord]:
        """Return newest-first run records, including legacy result directories."""

        if not self.root.exists():
            return []
        records: list[RunRecord] = []
        for directory in self.root.iterdir():
            if not directory.is_dir():
                continue
            record = self._read_record(directory)
            if record is None:
                continue
            if successful_only and record.status != RunStatus.SUCCESS:
                continue
            records.append(record)
        return sorted(records, key=lambda item: item.updated_at, reverse=True)

    def load_summary(self, run_id: str) -> dict[str, Any]:
        """Load one successful run summary."""

        path = self.root / run_id / "summary.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid summary for run {run_id}")
        return {str(key): value for key, value in raw.items()}

    def load_config(self, run_id: str) -> dict[str, Any]:
        """Load one run's immutable configuration snapshot."""

        path = self.root / run_id / "config.snapshot.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"Invalid config snapshot for run {run_id}")
        return {str(key): value for key, value in raw.items()}

    def comparison_frame(self, run_ids: list[str]) -> pd.DataFrame:
        """Build one row per run for tables and CSV export."""

        rows: list[dict[str, Any]] = []
        for run_id in run_ids:
            summary = self.load_summary(run_id)
            config = self.load_config(run_id)
            strategy = _mapping(_mapping(config.get("strategy")).get("strategy"))
            backtest = _mapping(_mapping(config.get("app")).get("backtest"))
            rows.append(
                {
                    "run_id": run_id,
                    "strategy": strategy.get("plugin"),
                    "parameters": json.dumps(
                        strategy.get("parameters", {}), ensure_ascii=False, sort_keys=True
                    ),
                    "start_date": backtest.get("start_date"),
                    "end_date": backtest.get("end_date"),
                    **summary,
                }
            )
        return pd.DataFrame(rows)

    def normalized_nav(self, run_ids: list[str]) -> pd.DataFrame:
        """Join selected equity curves after normalizing each to one."""

        merged: pd.DataFrame | None = None
        for run_id in run_ids:
            nav = pd.read_parquet(self.root / run_id / "nav.parquet")
            if nav.empty:
                continue
            series = nav[["trade_date", "equity"]].copy()
            series["trade_date"] = pd.to_datetime(series["trade_date"])
            equity = pd.to_numeric(series["equity"], errors="coerce")
            first = equity.dropna().iloc[0]
            series = series.assign(**{run_id: equity / first}).drop(columns="equity")
            merged = (
                series if merged is None else merged.merge(series, on="trade_date", how="outer")
            )
        return merged.sort_values("trade_date") if merged is not None else pd.DataFrame()

    def _update(self, run_id: str, status: RunStatus, error: str | None = None) -> None:
        directory = self.root / run_id
        path = directory / "run.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.update(
            {
                "status": status.value,
                "updated_at": datetime.now(UTC).isoformat(),
                "error": error,
            }
        )
        self._write(directory, raw)

    def _read_record(self, directory: Path) -> RunRecord | None:
        lifecycle = directory / "run.json"
        if lifecycle.exists():
            raw = json.loads(lifecycle.read_text(encoding="utf-8"))
            strategy_id = str(raw.get("strategy_id", ""))
            return RunRecord(
                run_id=str(raw.get("run_id", directory.name)),
                status=RunStatus(str(raw.get("status", RunStatus.FAILED.value))),
                created_at=str(raw.get("created_at", "")),
                updated_at=str(raw.get("updated_at", "")),
                strategy_plugin=str(raw.get("strategy_plugin", "")),
                strategy_id=strategy_id,
                start_date=str(raw.get("start_date", "")),
                end_date=str(raw.get("end_date", "")),
                error=(str(raw["error"]) if raw.get("error") else None),
                path=directory,
                run_kind=str(raw.get("run_kind") or _infer_run_kind(strategy_id)),
                parent_experiment_id=(
                    str(raw["parent_experiment_id"])
                    if raw.get("parent_experiment_id")
                    else None
                ),
                baseline_run_id=(
                    str(raw["baseline_run_id"]) if raw.get("baseline_run_id") else None
                ),
            )
        if not (directory / "summary.json").exists():
            return None
        timestamp = datetime.fromtimestamp(directory.stat().st_mtime, UTC).isoformat()
        strategy_plugin = ""
        strategy_id = ""
        start_date = ""
        end_date = ""
        run_kind = "single"
        parent_experiment_id: str | None = None
        baseline_run_id: str | None = None
        snapshot = directory / "config.snapshot.yaml"
        if snapshot.exists():
            config = yaml.safe_load(snapshot.read_text(encoding="utf-8")) or {}
            strategy = _mapping(_mapping(config.get("strategy")).get("strategy"))
            backtest = _mapping(_mapping(config.get("app")).get("backtest"))
            strategy_plugin = str(strategy.get("plugin", ""))
            strategy_id = str(strategy.get("id", ""))
            start_date = str(backtest.get("start_date", ""))
            end_date = str(backtest.get("end_date", ""))
            run_kind = str(
                backtest.get("run_kind")
                or _infer_run_kind(strategy_id, str(backtest.get("evaluation_mode", "")))
            )
            parent_experiment_id = (
                str(backtest["parent_experiment_id"])
                if backtest.get("parent_experiment_id")
                else None
            )
            baseline_run_id = (
                str(backtest["baseline_run_id"])
                if backtest.get("baseline_run_id")
                else None
            )
        return RunRecord(
            directory.name,
            RunStatus.SUCCESS,
            timestamp,
            timestamp,
            strategy_plugin,
            strategy_id,
            start_date,
            end_date,
            None,
            directory,
            run_kind,
            parent_experiment_id,
            baseline_run_id,
        )

    @staticmethod
    def _write(directory: Path, value: dict[str, Any]) -> None:
        target = directory / "run.json"
        temporary = directory / "run.json.tmp"
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(target)


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _infer_run_kind(strategy_id: str, evaluation_mode: str = "") -> str:
    if evaluation_mode == "out_of_sample" or ("_wf" in strategy_id and "_test" in strategy_id):
        return "walk_forward_oos"
    if "_opt_" in strategy_id or evaluation_mode == "training":
        return "optimization"
    return "single"
