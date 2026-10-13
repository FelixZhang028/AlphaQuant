"""Benchmark comparison shown with a backtest result, read from the run's own files."""
import json
import sqlite3
from contextlib import contextmanager
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant import run_evidence
from app.quant.benchmark_view import benchmark_comparison, benchmark_options
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


def index_bars(symbol, closes, start="2025-01-02"):
    return pd.DataFrame({"symbol": symbol, "trade_date": pd.bdate_range(start, periods=len(closes)), "raw_close": closes})


FULL_SUMMARY = {**SUMMARY, "initial_cash": 100.0, "cumulative_return": 0.15, "annualization": 252, "risk_free_rate": 0.0}


def test_another_index_is_recomputed_from_local_bars_the_way_the_engine_anchors_its_own(tmp_path):
    directory = save(tmp_path / "run", [100, 104, 110, 115], [100, 120, 90, 110], FULL_SUMMARY)
    # 同样的走势换一个名字：数字应当和引擎保存的沪深 300 曲线一致。
    bars = pd.concat([index_bars("000905.SH", [2000, 2400, 1800, 2200]), index_bars("000852.SH", [50, 51, 52, 53])])
    other = benchmark_comparison(directory, "000905.SH", bars)
    recorded = benchmark_comparison(directory)
    assert (other["symbol"], other["name"]) == ("000905.SH", "中证 500")
    assert other["benchmark_curve"] == recorded["benchmark_curve"] and other["strategy_curve"] == recorded["strategy_curve"]
    assert (other["benchmark_return"], other["excess_return"], other["benchmark_max_drawdown"]) == (10.0, 5.0, 25.0)
    assert other["beta"] is not None and other["tracking_error"] is not None
    # 选回记录里的基准时，用的是引擎保存的数字。
    assert benchmark_comparison(directory, "000300.SH", bars) == recorded


def test_an_index_that_starts_late_or_stops_early_is_not_compared(tmp_path):
    equity = [100 + step for step in range(12)]
    directory = save(tmp_path / "run", equity, [100] * 12, FULL_SUMMARY)
    late = benchmark_comparison(directory, "000905.SH", index_bars("000905.SH", [10] * 10, start="2025-01-06"))
    assert late == {"symbol": "000905.SH", "name": "中证 500", "comparable": False, "benchmark_start": "2025-01-06"}
    # 行情比回测早结束 6 个交易日：超过允许的 5 天。
    stopped = benchmark_comparison(directory, "000905.SH", index_bars("000905.SH", [10, 11, 12, 13, 14, 15]))
    assert stopped == {"symbol": "000905.SH", "name": "中证 500", "comparable": False, "benchmark_end": "2025-01-09"}
    # 只晚一两天更新是常见情况，仍然比较，缺的那几天沿用最后一个值。
    recent = benchmark_comparison(directory, "000905.SH", index_bars("000905.SH", [10 + step for step in range(10)]))
    assert recent["comparable"] and recent["benchmark_curve"][-3:] == [90.0, 90.0, 90.0]


def test_indices_without_usable_bars_cannot_be_chosen(tmp_path):
    directory = save(tmp_path / "run", [100, 104, 110, 115], [100, 120, 90, 110], FULL_SUMMARY)
    bars = index_bars("000905.SH", [10, 11, 12, 13], start="2030-01-01")
    # 有行情但完全在回测之后（或之前）：说明行情从哪天开始、到哪天为止。
    assert benchmark_comparison(directory, "000905.SH", bars) == {
        "symbol": "000905.SH", "name": "中证 500", "comparable": False, "benchmark_start": "2030-01-01"}
    assert benchmark_comparison(directory, "000905.SH", index_bars("000905.SH", [10, 11], start="2020-01-01")) == {
        "symbol": "000905.SH", "name": "中证 500", "comparable": False, "benchmark_end": "2020-01-02"}
    assert benchmark_comparison(directory, "000852.SH", bars) is None
    assert benchmark_comparison(directory, "000905.SH") is None
    listed = benchmark_options(pd.concat([index_bars("000852.SH", [1, 2]), index_bars("000300.SH", [1, 2, 3]), index_bars("999999.XX", [1])]))
    assert listed == [{"symbol": "000300.SH", "name": "沪深 300", "start_date": "2025-01-02", "end_date": "2025-01-06"},
                      {"symbol": "000852.SH", "name": "中证 1000", "start_date": "2025-01-02", "end_date": "2025-01-03"}]
    assert benchmark_options(pd.DataFrame()) == []


def test_the_result_endpoint_carries_the_comparison_for_runs_made_earlier(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evidence, "RUNTIME_ROOT", tmp_path)
    bars = pd.concat([index_bars("000300.SH", [3000, 3600, 2700, 3300]), index_bars("000905.SH", [2000, 2100, 2200, 2300])])
    monkeypatch.setattr(backtests, "market_repository", lambda: SimpleNamespace(read_table=lambda name: bars))
    directory = save(tmp_path / "runs" / "1", [100, 104, 110, 115], [100, 120, 90, 110], FULL_SUMMARY)
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
    detail = client.get("/api/v1/backtests/1").json()
    assert detail["benchmark"]["excess_return"] == 5.0
    assert [item["symbol"] for item in detail["benchmark_options"]] == ["000300.SH", "000905.SH"]
    legacy = client.get("/api/v1/backtests/2").json()
    assert legacy["benchmark"] is None and legacy["benchmark_options"] == []

    # 换一个指数比较
    other = client.get("/api/v1/backtests/1/benchmark", params={"symbol": "000905.SH"}).json()
    assert (other["name"], other["benchmark_return"], other["excess_return"]) == ("中证 500", 15.0, 0.0)
    assert client.get("/api/v1/backtests/1/benchmark", params={"symbol": "000852.SH"}).status_code == 404
    assert client.get("/api/v1/backtests/1/benchmark", params={"symbol": "600519.SH"}).status_code == 422
    assert client.get("/api/v1/backtests/2/benchmark", params={"symbol": "000905.SH"}).status_code == 404
    assert client.get("/api/v1/backtests/9/benchmark", params={"symbol": "000905.SH"}).status_code == 404
