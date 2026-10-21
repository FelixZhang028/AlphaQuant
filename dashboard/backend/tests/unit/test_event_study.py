"""事件研究：满足条件以后通常怎么样，和全部交易日对照；同一只股票冷却期内不重复计算；
ST、上市不久、停牌不计入；之后退市的单独数出来；只用当天以前的数据。"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.research import event_study as es

DAYS = pd.bdate_range("2024-01-01", periods=420)
DROP = 300                                     # 第 300 天跌到底


def path(kind):
    price = np.full(len(DAYS), 10.0)
    if kind in ("drop", "st", "gone"):
        price[DROP - 20:DROP + 1] = np.linspace(10.0, 7.0, 21)     # 20 个交易日跌 30%
        price[DROP + 1:] = np.linspace(7.0, 7.7, len(DAYS) - DROP - 1)
    return price


def bars_for(symbol, kind):
    price = path(kind)
    days = DAYS
    if kind == "new":
        days, price = DAYS[-30:], price[-30:]                       # 上市只有 30 天
    if kind == "gone":
        days, price = DAYS[:DROP + 5], price[:DROP + 5]             # 跌完 5 天后退市
    return pd.DataFrame({"symbol": symbol, "trade_date": days, "adjusted_close": price, "raw_close": price,
                         "amount": 1e8, "is_st": kind == "st", "is_suspended": False,
                         "up_limit": price * 1.1, "down_limit": price * 0.9})


@pytest.fixture
def repository(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    kinds = {"600000.SH": "drop", "600001.SH": "st", "600002.SH": "new", "600003.SH": "gone"}
    kinds.update({f"6001{i:02d}.SH": "flat" for i in range(10)})
    repo.save_table("daily_bars", pd.concat([bars_for(symbol, kind) for symbol, kind in kinds.items()], ignore_index=True))
    return repo


FALL = {"type": "ret", "days": 20, "op": "<=", "value": -20}


def test_conditions_are_checked_and_described():
    assert es.clean_condition(FALL)["label"] == "近 20 个交易日涨跌幅 ≤ -20%"
    assert es.clean_condition({"type": "ma_cross", "days": 60, "direction": "up"})["label"] == "收盘价当天从下往上穿过 60 日均线"
    assert es.clean_condition({"type": "limit", "direction": "down"})["label"] == "当天跌停"
    assert es.clean_condition({"type": "pe", "op": ">=", "value": 30})["label"] == "市盈率（TTM，只算盈利的公司） ≥ 30"
    for bad, reason in [({"type": "nope"}, "不认识"), ({**FALL, "days": 7}, "天数"), ({**FALL, "op": "<"}, "比较方式"),
                        ({**FALL, "value": "abc"}, "数字"), ({"type": "from_high", "op": "<=", "value": 20}, "之间")]:
        with pytest.raises(es.EventStudyError, match=reason):
            es.clean_condition(bad)


def test_one_episode_counts_once_per_cooling_off_period():
    events = np.zeros((40, 2), dtype=bool)
    events[5:15, 0] = True                     # 连续 10 天满足条件
    events[[3, 30], 1] = True
    kept = es.cool_down(events, 20)
    assert np.flatnonzero(kept[:, 0]).tolist() == [5] and np.flatnonzero(kept[:, 1]).tolist() == [3, 30]
    assert es.cool_down(events, 0).sum() == events.sum()


def test_events_are_measured_against_all_days(repository):
    result = es.run(repository, {"conditions": [FALL], "start": "2024-04-01"}, pool=[], names={"600000.SH": "下跌股份"})
    # 只有一直在交易、不是 ST、上市够久的那只下跌股票算；之后退市的那只单独数出来
    assert result["events"] == 2 and result["stocks"] == 2
    h20 = result["horizons"]["20"]
    assert h20["left_market"] == 1 and h20["events"]["count"] == 1
    first = DAYS.get_loc(pd.Timestamp(result["recent"][0]["date"]))
    expected = path("drop")[first + 20] / path("drop")[first] - 1
    assert h20["events"]["mean"] == pytest.approx(expected, abs=1e-5)
    assert h20["all"]["count"] > 1000 and abs(h20["all"]["median"]) < 1e-9      # 其他股票不涨不跌
    assert result["recent"][0]["name"] == "下跌股份" and result["recent"][0]["symbol"] == "600000"
    assert any("样本太少" in note for note in result["notes"])
    kept = es.run(repository, {"conditions": [FALL], "start": "2024-04-01", "keep_st": True}, pool=[], names={})
    assert kept["events"] == 3                                                     # 保留 ST 时多一只
    every_day = es.run(repository, {"conditions": [FALL], "start": "2024-04-01", "cooldown": 0}, pool=[], names={})
    assert every_day["events"] > result["events"]


def test_the_average_path_after_the_event(repository):
    result = es.run(repository, {"conditions": [FALL], "start": "2024-04-01"}, pool=[], names={})
    curve = result["path"]
    assert curve["days"][:3] == [0, 1, 2] and curve["days"][-1] == 60 and curve["events"][0] == 0
    for h in es.HORIZONS:                       # 和上面的数字一致
        i = curve["days"].index(h)
        assert curve["events"][i] == pytest.approx(result["horizons"][str(h)]["events"]["mean"], abs=1e-5)
        assert curve["all"][i] == pytest.approx(result["horizons"][str(h)]["all"]["mean"], abs=1e-5)
    # 两次事件（下跌股票和之后退市的那只）同一天、走势一样；同一天能比的 12 只股票里另外 10 只不涨不跌
    first = DAYS.get_loc(pd.Timestamp(result["recent"][0]["date"]))
    i7 = curve["days"].index(7)
    change = path("drop")[first + 7] / path("drop")[first] - 1
    assert curve["events"][i7] == pytest.approx(change, abs=1e-5)
    assert curve["market"][i7] == pytest.approx(change / 6, abs=1e-5)
    assert abs(curve["all"][i7]) < 0.01


def test_the_same_question_is_answered_from_memory(repository, monkeypatch):
    calls = []
    compute = es._compute
    monkeypatch.setattr(es, "_compute", lambda *args: calls.append(args[1]) or compute(*args))
    es.warm(repository, {})
    assert len(calls) == len(es.PRESETS)
    es.warm(repository, {})                                         # 同一份数据只预先算一次
    answer = es.run(repository, {"conditions": es.PRESETS[0][3]}, pool=[], names={})
    assert len(calls) == len(es.PRESETS)
    answer["events"] = -1                                           # 改返回值不影响记住的结果
    assert es.run(repository, {"conditions": es.PRESETS[0][3]}, pool=[], names={})["events"] != -1
    es.run(repository, {"conditions": es.PRESETS[0][3], "cooldown": 5}, pool=[], names={})
    assert len(calls) == len(es.PRESETS) + 1                        # 换了设置就重新算


def test_downloading_other_data_keeps_the_answers_that_do_not_use_it(repository, monkeypatch):
    calls = []
    compute = es._compute
    monkeypatch.setattr(es, "_compute", lambda *args: calls.append(args[1][0]["type"]) or compute(*args))
    cheap = {"type": "pe", "op": "<=", "value": 10}
    for conditions in ([FALL], [cheap]):
        es.run(repository, {"conditions": conditions, "cooldown": 60}, pool=[], names={})
    repository.save_table("daily_indicators", pd.DataFrame({"symbol": ["600000.SH"], "trade_date": [DAYS[-1]], "pe_ttm": [8.0]}))
    for conditions in ([FALL], [cheap]):
        es.run(repository, {"conditions": conditions, "cooldown": 60}, pool=[], names={})
    assert calls == ["ret", "pe", "pe"]                 # 只有用到估值数据的问题重新算


def test_the_pool_scope_and_bad_requests(repository):
    only_flat = es.run(repository, {"conditions": [FALL], "scope": "pool"}, pool=["600100.SH"], names={})
    assert only_flat["events"] == 0 and only_flat["scope"] == "我的股票池"
    for request, reason in [({"conditions": []}, "至少"), ({"conditions": [FALL] * 4}, "最多"),
                            ({"conditions": [FALL], "scope": "moon"}, "范围"), ({"conditions": [FALL], "cooldown": 7}, "冷却期"),
                            ({"conditions": [FALL], "start": "2025-06-01", "end": "2025-01-01"}, "早于")]:
        with pytest.raises(es.EventStudyError, match=reason):
            es.run(repository, request, pool=[], names={})
    with pytest.raises(es.EventStudyError, match="股票池是空的"):
        es.run(repository, {"conditions": [FALL], "scope": "pool"}, pool=[], names={})


def test_the_routes(repository, monkeypatch):
    monkeypatch.setattr(workspace, "market_repository", lambda: repository)
    monkeypatch.setattr(workspace, "security_names", lambda: {})
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda user_id: ["600000"])
    warmed = []
    monkeypatch.setattr(es, "warm_later", lambda repo, names: warmed.append(repo))
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "is_admin": False}
    client = TestClient(app)
    options = client.get("/api/v1/event-study/options").json()
    assert {c["type"] for c in options["conditions"]} >= {"ret", "from_high", "pe", "profit_yoy"}
    assert options["bounds"]["end"] == DAYS[-1].date().isoformat() and options["horizons"] == [5, 20, 60]
    assert options["presets"][0]["question"] == "大跌之后会反弹吗？" and warmed == [repository]
    for preset in options["presets"]:                               # 常见问题的条件都合法
        assert all(es.clean_condition(c) for c in preset["conditions"])
    body = client.post("/api/v1/event-study", json={"conditions": [FALL], "scope": "pool"}).json()
    assert body["events"] == 1 and body["conditions"] == ["近 20 个交易日涨跌幅 ≤ -20%"]
    assert client.post("/api/v1/event-study", json={"conditions": [{"type": "nope"}]}).status_code == 422
    assert client.post("/api/v1/event-study", json={"conditions": [FALL], "industry": "银行"}).status_code == 422
