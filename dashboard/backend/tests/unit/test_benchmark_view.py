"""Benchmark comparison shown with a backtest result, read from the run's own files."""
import json
import sqlite3
from contextlib import contextmanager

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant import run_evidence
from app.quant.benchmark_view import benchmark_comparison
from app.routes import backtests
from app.routes.auth import get_current_user

SUMMARY = {"benchmark_symbol": "000300.SH", "benchmark_return": 0.10, "excess_return": 0.05, "beta": 0.5712,
           "regression_alpha": 0.08, "information_ratio": 0.4, "tracking_error": 0.12}


def save(directory, equity, benchmark, summary=SUMMARY):
    directory.mkdir(parents=True, exist_ok=True)
    days = pd.bdate_range("2025-01-02", periods=len(equity))
    frame = pd.DataFrame({"trade_date": days, "equity": equity})
    if benchmark is not None:
        frame["benchmark_equity"] = benchmark
    frame.to_parquet(directory / "nav.parquet")
    (directory / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return directory


def test_curves_start_together_and_metrics_are_in_percent(tmp_path):
    result = benchmark_comparison(save(tmp_path / "run", [100, 104, 110, 115], [100, 120, 90, 110]))
    assert result["comparable"] and result["name"] == "沪深 300" and result["symbol"] == "000300.SH"
    assert result["strategy_curve"] == [0.0, 4.0, 10.0, 15.0]
    assert result["benchmark_curve"] == [0.0, 20.0, -10.0, 10.0]
    assert (result["benchmark_return"], result["excess_return"]) == (10.0, 5.0)
    # 基准从 120 跌到 90。
    assert result["benchmark_max_drawdown"] == 25.0
    assert (result["beta"], result["alpha"], result["information_ratio"], result["tracking_error"]) == (0.57, 8.0, 0.4, 12.0)


def test_a_benchmark_that_starts_late_is_not_compared(tmp_path):
    result = benchmark_comparison(save(tmp_path / "run", [100, 104, 110, 115], [None, None, 100, 110]))
    assert result == {"symbol": "000300.SH", "name": "沪深 300", "comparable": False, "benchmark_start": "2025-01-06"}


def test_days_without_a_benchmark_bar_keep_the_previous_value_and_undefined_metrics_stay_empty(tmp_path):
    summary = {**SUMMARY, "beta": None, "information_ratio": float("nan")}
    result = benchmark_comparison(save(tmp_path / "run", [100, 104, 110, 115], [100, None, 105, 110], summary))
    assert result["benchmark_curve"] == [0.0, 0.0, 5.0, 10.0]
    assert result["beta"] is None and result["information_ratio"] is None


@pytest.mark.parametrize("benchmark", [None, [None, None, None, None], [None, None, None, 100]])
def test_runs_without_benchmark_data_have_no_comparison(tmp_path, benchmark):
    assert benchmark_comparison(save(tmp_path / "run", [100, 104, 110, 115], benchmark)) is None


def test_missing_or_broken_run_files_have_no_comparison(tmp_path):
    assert benchmark_comparison(None) is None
    assert benchmark_comparison(tmp_path / "absent") is None
    directory = save(tmp_path / "run", [100, 104], [100, 101])
    (directory / "summary.json").write_text("not json", encoding="utf-8")
    assert benchmark_comparison(directory) is None


def test_the_result_endpoint_carries_the_comparison_for_runs_made_earlier(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evidence, "RUNTIME_ROOT", tmp_path)
    directory = save(tmp_path / "runs" / "1", [100, 104, 110, 115], [100, 120, 90, 110])
    db = tmp_path / "test.db"

    @contextmanager
    def connect():
        with sqlite3.connect(db) as conn:
            conn.row_factory = sqlite3.Row
            yield conn

    with connect() as conn:
        conn.execute("CREATE TABLE backtests (id INTEGER PRIMARY KEY, user_id INTEGER, strategy TEXT, market TEXT, from_date TEXT, to_date TEXT, status TEXT, result TEXT, created_at TEXT)")
        # 入库的结果里没有基准：它是查看时从运行目录读出来的。
        for number, stored in ((1, {"output_dir": str(directory)}), (2, {})):
            conn.execute("INSERT INTO backtests VALUES (?,?,?,?,?,?,?,?,?)",
                         (number, 1, "s", "当前股票池", "2025-01-02", "2025-01-07", "完成", json.dumps(stored), "2025-01-08"))
    monkeypatch.setattr(backtests, "get_conn", connect)
    app = FastAPI()
    app.include_router(backtests.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    client = TestClient(app)
    assert client.get("/api/v1/backtests/1").json()["benchmark"]["excess_return"] == 5.0
    assert client.get("/api/v1/backtests/2").json()["benchmark"] is None
