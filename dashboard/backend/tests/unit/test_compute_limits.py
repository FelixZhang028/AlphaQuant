"""Heavy computations share the server: one per user, a few at once, a time limit, and reuse of results."""
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.quant import compute
from app.routes import backtests, workspace
from app.routes.auth import get_current_user
from quant_platform.application.backtest_service import BacktestService
from quant_platform.core import deadline
from quant_platform.core.deadline import ComputationTimeout
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.factors.registry import default_registry
from test_factor_index_universe import DAYS, HS300, market


@pytest.fixture
def two_slots(monkeypatch):
    monkeypatch.setattr(compute, "slots", lambda: 2)
    monkeypatch.setattr(compute, "per_user", lambda: 1)


def test_one_computation_per_user_and_a_few_at_once(two_slots):
    with compute.computing({"id": 1}):
        with pytest.raises(HTTPException) as busy:
            with compute.computing({"id": 1}):
                pass
        assert busy.value.status_code == 429 and "你有一个计算正在进行" in busy.value.detail
        with compute.computing({"id": 2}):
            assert compute.running() == {"total": 2, "users": 2}
            with pytest.raises(HTTPException) as full:
                with compute.computing({"id": 3}):
                    pass
            assert full.value.status_code == 429 and "服务器正忙" in full.value.detail
    assert compute.running() == {"total": 0, "users": 0}          # 用完都还回去，出错也一样
    with pytest.raises(ValueError):
        with compute.computing({"id": 1}):
            raise ValueError("引擎出错")
    assert compute.running() == {"total": 0, "users": 0}


def test_a_computation_past_its_time_limit_stops_at_the_next_safe_point(two_slots, monkeypatch):
    monkeypatch.setattr(compute, "timeout_seconds", lambda: 0.05)
    steps = []
    with pytest.raises(HTTPException) as stopped:
        with compute.computing({"id": 1}):
            for step in range(100):
                deadline.check()
                steps.append(step)
                time.sleep(0.01)
    assert stopped.value.status_code == 422 and "计算超过了 1 分钟，已经停止" in stopped.value.detail
    assert 0 < len(steps) < 100 and compute.running()["total"] == 0
    deadline.check()                                                 # 计算结束后不再限时


def test_the_stop_is_not_swallowed_by_code_that_skips_failures():
    # 库里常有“这一项出错就跳过”的 except Exception：超时必须穿过它，不能当成一个普通错误继续算。
    def skip_failures():
        for _ in range(3):
            try:
                deadline.check()
            except Exception:  # noqa: BLE001
                continue
        return "继续算完了"

    with deadline.limit(-1), pytest.raises(ComputationTimeout):
        skip_failures()


def test_long_loops_check_the_time(tmp_path):
    repo = market(tmp_path)
    factor = default_registry().get("momentum_20")
    with deadline.limit(-1), pytest.raises(ComputationTimeout):
        FactorEvaluator(repo).evaluate(factor, DAYS[25].date(), DAYS[-1].date(), horizon=1, n_groups=3)


def test_a_backtest_stopped_for_time_is_recorded_as_failed(tmp_path, monkeypatch):
    service = BacktestService("configs/app.yaml")
    service.configs["app"]["app"]["runtime_dir"] = str(tmp_path)
    monkeypatch.setattr(service, "build_engine", lambda request: (SimpleNamespace(run=lambda *a, **k: deadline.check()), None))
    with deadline.limit(-1), pytest.raises(ComputationTimeout):
        service.run(service.default_request())
    (record,) = service.run_store.list_records()
    assert record.status == "FAILED" and "ComputationTimeout" in record.error


# --------------------------------------------------------------------------- #
# 结果复用
# --------------------------------------------------------------------------- #


def test_the_same_request_on_the_same_data_is_computed_once(tmp_path):
    data = tmp_path / "market"
    data.mkdir()
    (data / "daily_bars.parquet").write_bytes(b"v1")
    calls = []

    def work():
        calls.append(1)
        return {"ic": 0.05, "rows": [{"date": "2025-01-02", "value": 1}]}

    first = compute.cached("factor_evaluate", {"id": 1}, {"factor": "a"}, data, work)
    first["ic"] = 99                                                  # 改返回值不会改到存着的结果
    assert compute.cached("factor_evaluate", {"id": 1}, {"factor": "a"}, data, work)["ic"] == 0.05 and len(calls) == 1
    compute.cached("factor_evaluate", {"id": 2}, {"factor": "a"}, data, work)          # 每个用户各自的
    compute.cached("factor_evaluate", {"id": 1}, {"factor": "b"}, data, work)          # 请求不同
    assert len(calls) == 3
    time.sleep(0.01)
    (data / "daily_bars.parquet").write_bytes(b"v2 after the daily update")              # 数据更新了
    compute.cached("factor_evaluate", {"id": 1}, {"factor": "a"}, data, work)
    assert len(calls) == 4


def test_failures_are_not_remembered_and_old_results_make_room(tmp_path, monkeypatch):
    monkeypatch.setattr(compute, "cache_size", lambda: 2)
    calls = []

    def failing():
        calls.append("x")
        raise HTTPException(status_code=422, detail="样本不足")

    for _ in range(2):
        with pytest.raises(HTTPException):
            compute.cached("factor_evaluate", {"id": 1}, {"f": "bad"}, tmp_path, failing)
    assert calls == ["x", "x"]
    for name in ("a", "b", "c"):
        compute.cached("factor_evaluate", {"id": 1}, {"f": name}, tmp_path, lambda name=name: calls.append(name) or {"f": name})
    compute.cached("factor_evaluate", {"id": 1}, {"f": "a"}, tmp_path, lambda: calls.append("a again") or {"f": "a"})
    assert calls[-1] == "a again"                                     # 最早的一份已经让出位置


def test_a_cached_result_does_not_take_a_slot(tmp_path):
    compute.cached("factor_evaluate", {"id": 1}, {"f": "a"}, tmp_path, lambda: {"f": "a"})
    with compute.computing({"id": 1}):                                 # 这个用户正在算别的
        assert compute.cached("factor_evaluate", {"id": 1}, {"f": "a"}, tmp_path, lambda: {"f": "new"}) == {"f": "a"}


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = market(tmp_path)
    monkeypatch.setattr(workspace, "market_repository", lambda: repo)
    monkeypatch.setattr("app.quant.markets.market_repository", lambda: repo)
    monkeypatch.setattr(workspace, "local_data_bounds", lambda: (DAYS[0].date(), DAYS[-1].date()))
    app = FastAPI()
    app.include_router(workspace.router)
    app.include_router(backtests.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    return TestClient(app)


def test_evaluating_the_same_factor_again_is_answered_from_memory(client, monkeypatch):
    evaluated = []
    original = FactorEvaluator.evaluate
    monkeypatch.setattr(FactorEvaluator, "evaluate", lambda self, *a, **k: evaluated.append(1) or original(self, *a, **k))
    body = {"factor_name": "momentum_20", "start_date": DAYS[25].date().isoformat(), "end_date": DAYS[-1].date().isoformat(), "universe": HS300}
    first = client.post("/api/v1/factors/evaluate", json=body)
    second = client.post("/api/v1/factors/evaluate", json=body)
    assert first.status_code == second.status_code == 200 and first.json() == second.json() and len(evaluated) == 1
    client.post("/api/v1/factors/evaluate", json={**body, "horizon": 2})
    assert len(evaluated) == 2


def test_a_user_with_a_computation_running_is_told_to_wait(client):
    body = {"factor_name": "momentum_20", "start_date": DAYS[25].date().isoformat(), "end_date": DAYS[-1].date().isoformat(), "universe": HS300}
    backtest = {"strategy": "a_share_momentum", "market": "当前股票池", "from_date": "2025-01-06", "to_date": "2025-03-31",
                "initial_capital": 100000, "max_positions": 5, "rebalance": "weekly"}
    holding = threading.Event()
    release = threading.Event()

    def busy():
        with compute.computing({"id": 1}):
            holding.set()
            release.wait(5)

    worker = threading.Thread(target=busy)
    worker.start()
    try:
        holding.wait(5)
        for path, payload in (("/api/v1/factors/evaluate", body), ("/api/v1/backtests", backtest)):
            response = client.post(path, json=payload)
            assert response.status_code == 429 and "你有一个计算正在进行" in response.json()["detail"], path
    finally:
        release.set()
        worker.join()
    assert client.post("/api/v1/factors/evaluate", json=body).status_code == 200
