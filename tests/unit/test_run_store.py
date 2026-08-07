from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from quant_platform.backtest.run_store import BacktestRunStore, RunStatus


def _snapshot() -> dict[str, object]:
    return {
        "strategy": {
            "strategy": {
                "plugin": "momentum",
                "id": "test",
                "parameters": {"lookback": 20},
            }
        },
        "app": {
            "backtest": {
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "run_kind": "optimization",
                "parent_experiment_id": "experiment-1",
                "baseline_run_id": "baseline-1",
            }
        },
    }


def test_run_store_tracks_lifecycle_and_builds_comparison(tmp_path: Path) -> None:
    store = BacktestRunStore(tmp_path / "runs")
    directory = store.start("run-1", _snapshot())
    store.mark_running("run-1")
    (directory / "summary.json").write_text(json.dumps({"annual_return": 0.1}), encoding="utf-8")
    (directory / "config.snapshot.yaml").write_text(yaml.safe_dump(_snapshot()), encoding="utf-8")
    pd.DataFrame({"trade_date": ["2024-01-01", "2024-01-02"], "equity": [100.0, 110.0]}).to_parquet(
        directory / "nav.parquet", index=False
    )
    store.complete("run-1")

    record = store.list_records(successful_only=True)[0]
    comparison = store.comparison_frame(["run-1"])
    nav = store.normalized_nav(["run-1"])

    assert record.status == RunStatus.SUCCESS
    assert record.strategy_plugin == "momentum"
    assert record.run_kind == "optimization"
    assert record.parent_experiment_id == "experiment-1"
    assert record.baseline_run_id == "baseline-1"
    assert comparison.iloc[0]["annual_return"] == 0.1
    assert nav["run-1"].tolist() == [1.0, 1.1]


def test_run_store_preserves_failed_run(tmp_path: Path) -> None:
    store = BacktestRunStore(tmp_path / "runs")
    store.start("failed", _snapshot())
    store.fail("failed", ValueError("bad parameters"))

    record = store.list_records()[0]

    assert record.status == RunStatus.FAILED
    assert "bad parameters" in str(record.error)
