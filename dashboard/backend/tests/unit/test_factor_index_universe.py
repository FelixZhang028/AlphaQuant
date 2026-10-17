"""Factor research on an index as it was: only each day's members are samples, and Alpha101 ranks only among them."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.data.index_constituents import (
    CHECKS_TABLE,
    CONSTITUENTS_TABLE,
    UNIVERSE_COLUMN,
    IndexUniverseRepository,
    mark_members,
    membership,
)
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors import alpha101
from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.factors.registry import default_registry

HS300 = "000300.SH"
DAYS = pd.bdate_range("2025-01-06", periods=60)
SYMBOLS = [f"{number:06d}.SZ" for number in range(1, 13)]
SWITCH = DAYS[30]          # 第 31 天：000001 出指数，000012 进指数


def market(tmp_path):
    rng = np.random.default_rng(7)
    frames = []
    for index, symbol in enumerate(SYMBOLS):
        close = 10 * np.cumprod(1 + rng.normal(0.0005 * index, 0.02, len(DAYS)))
        frames.append(pd.DataFrame({"symbol": symbol, "trade_date": DAYS, "raw_open": close * 0.99, "raw_high": close * 1.02,
                                    "raw_low": close * 0.98, "raw_close": close, "pre_close": close, "volume": rng.uniform(1e5, 2e5, len(DAYS)),
                                    "amount": 1e6, "adjusted_close": close, "adj_factor": 1.0, "quality_status": "OK", "source": "baostock"}))
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", pd.concat(frames, ignore_index=True))
    first = SYMBOLS[:10]                       # 000001 ~ 000010
    second = SYMBOLS[1:10] + [SYMBOLS[11]]     # 000001 出，000012 进；000011 从来不是成分股
    repo.save_table(CONSTITUENTS_TABLE, pd.DataFrame(
        [{"index_symbol": HS300, "effective_date": DAYS[0], "symbol": symbol} for symbol in first]
        + [{"index_symbol": HS300, "effective_date": SWITCH, "symbol": symbol} for symbol in second]))
    repo.save_table(CHECKS_TABLE, pd.DataFrame([{"index_symbol": HS300, "checked_from": DAYS[0], "checked_through": DAYS[-1]}]))
    return repo


def test_bars_are_marked_by_membership_on_each_day(tmp_path):
    repo = market(tmp_path)
    scope = IndexUniverseRepository(repo, HS300, DAYS[0].date(), DAYS[-1].date())
    assert scope.symbols == SYMBOLS[:10] + [SYMBOLS[11]]                     # 从来不是成分股的不读
    bars = scope.get_daily_bars()
    assert set(bars["symbol"]) == set(scope.symbols)
    flag = bars.set_index(["symbol", "trade_date"])[UNIVERSE_COLUMN]
    assert flag[(SYMBOLS[0], DAYS[29])] and not flag[(SYMBOLS[0], SWITCH)]   # 调出的那天起不算
    assert not flag[(SYMBOLS[11], DAYS[29])] and flag[(SYMBOLS[11], SWITCH)]
    assert bars.groupby("trade_date")[UNIVERSE_COLUMN].sum().eq(10).all()
    assert scope.read_table(CHECKS_TABLE).equals(repo.read_table(CHECKS_TABLE))   # 其余的照原样
    # 指定股票时，不是成分股的不读。
    assert set(scope.get_daily_bars(symbols=[SYMBOLS[0], SYMBOLS[10]])["symbol"]) == {SYMBOLS[0]}
    assert mark_members(bars.iloc[:0], membership(repo.read_table(CONSTITUENTS_TABLE), HS300)).empty
    with pytest.raises(ValueError, match="从 2025-01-06 开始"):
        IndexUniverseRepository(repo, HS300, date(2024, 12, 2), DAYS[-1].date())


def test_an_evaluation_only_uses_each_days_members(tmp_path):
    repo = market(tmp_path)
    scope = IndexUniverseRepository(repo, HS300, DAYS[25].date(), DAYS[-1].date())
    factor = default_registry().get("momentum_20")
    report = FactorEvaluator(scope).evaluate(factor, DAYS[25].date(), DAYS[-1].date(), symbols=scope.symbols, horizon=5, n_groups=5)
    assert "每天只用当天的成分股（平均每天 10 只）" in " ".join(report.notes)
    # 用全部 12 只评估得到的 IC 不一样：样本不同。
    everyone = FactorEvaluator(repo).evaluate(factor, DAYS[25].date(), DAYS[-1].date(), symbols=SYMBOLS, horizon=5, n_groups=5)
    assert report.rank_ic_mean != pytest.approx(everyone.rank_ic_mean)
    assert not any("成分股" in note for note in everyone.notes)


def test_alpha101_ranks_only_among_that_days_members(tmp_path):
    repo = market(tmp_path)
    scope = IndexUniverseRepository(repo, HS300, DAYS[0].date(), DAYS[-1].date())
    marked = scope.get_daily_bars()
    formula = next(factor for factor in alpha101_factors() if factor.name == "alpha101_020")
    inside = formula.compute(marked).set_index(["date", "symbol"])["value"]
    plain = formula.compute(marked.drop(columns=[UNIVERSE_COLUMN])).set_index(["date", "symbol"])["value"]
    day = pd.Timestamp(DAYS[40])
    assert (day, SYMBOLS[0]) not in inside.index and np.isfinite(plain[(day, SYMBOLS[0])])   # 调出以后不参与排名，没有值
    members = [symbol for symbol in SYMBOLS[1:10]]
    assert not np.allclose(inside.loc[day].reindex(members), plain.loc[day].reindex(members))  # 排名的对象变了
    # 掩码只在这一次计算里有效。
    assert alpha101._UNIVERSE.get() is None
    frame = pd.DataFrame({"a": [1.0, 2.0], "b": [3.0, 1.0], "c": [2.0, 3.0]})
    token = alpha101._UNIVERSE.set(pd.DataFrame({"a": [True, True], "b": [True, False], "c": [False, True]}))
    try:
        ranked = alpha101.rank(frame)
    finally:
        alpha101._UNIVERSE.reset(token)
    assert ranked.iloc[0].tolist()[:2] == [0.5, 1.0] and np.isnan(ranked.iloc[0, 2])
    assert np.isnan(ranked.iloc[1, 1]) and ranked.iloc[1, [0, 2]].tolist() == [0.5, 1.0]


@pytest.fixture
def client(tmp_path, monkeypatch):
    repo = market(tmp_path)
    monkeypatch.setattr(workspace, "market_repository", lambda: repo)
    monkeypatch.setattr("app.quant.markets.market_repository", lambda: repo)
    monkeypatch.setattr(workspace, "local_data_bounds", lambda: (DAYS[0].date(), DAYS[-1].date()))
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    return TestClient(app)


def test_the_routes_offer_and_accept_an_index(client):
    items = client.get("/api/v1/factors/universes").json()["items"]
    assert [item["value"] for item in items] == ["当前股票池", HS300, "000016.SH", "000905.SH"]
    assert items[1]["available"] and not items[2]["available"]
    body = {"factor_name": "momentum_20", "start_date": DAYS[25].date().isoformat(), "end_date": DAYS[-1].date().isoformat(), "universe": HS300}
    response = client.post("/api/v1/factors/evaluate", json=body)
    assert response.status_code == 200, response.text
    assert "每天只用当天的成分股" in response.json()["notes"]          # 说明是连在一起的一段文字
    assert "还没有上证50" in client.post("/api/v1/factors/evaluate", json={**body, "universe": "000016.SH"}).json()["detail"]
    assert "不支持这个股票范围" in client.post("/api/v1/factors/evaluate", json={**body, "universe": "纳斯达克"}).json()["detail"]
