"""今天符合条件的股票：和回测同一套判断，按排序列出，排除 ST、停牌和当天没有行情的股票。"""

from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quant_platform.strategies.rule_based import rank_score
from quant_platform.strategies.rule_schema import RuleStrategyDefinition
from quant_platform.strategies.screen import screen

DAY = date(2026, 10, 21)


def definition(**ranking):
    return RuleStrategyDefinition.from_mapping({
        "strategy_id": "t", "name": "t", "entry_logic": "all",
        "entry_rules": [{"left": {"name": "close"}, "operator": "greater_than", "right": {"name": "moving_average", "window": 5}}],
        "ranking": {"indicator": {"name": "return", "window": 3}, **(ranking or {"direction": "descending"})},
    })


def history(symbol, closes, *, last=DAY, st=False, suspended=False):
    days = [last - timedelta(days=len(closes) - 1 - i) for i in range(len(closes))]
    rows = []
    for i, (day, close) in enumerate(zip(days, closes)):
        rows.append({"symbol": symbol, "trade_date": pd.Timestamp(day), "adjusted_close": close, "raw_close": close,
                     "pre_close": closes[i - 1] if i else close, "amount": 1e8,
                     "is_st": st and day == last, "is_suspended": suspended and day == last})
    return rows


def bars():
    rising = [10, 10, 10, 10, 10, 11, 12, 13]            # 在 5 日均线上方，近 3 日涨得最多
    slow = [10, 10, 10, 10, 10, 10, 10.2, 10.4]          # 在均线上方，涨得少
    falling = [13, 13, 13, 13, 13, 12, 11, 10]           # 在均线下方：不符合
    return pd.DataFrame(history("600001.SH", rising) + history("600002.SH", slow) + history("600003.SH", falling)
                        + history("600004.SH", rising, st=True)                  # ST：默认排除
                        + history("600005.SH", rising, suspended=True)           # 停牌：排除
                        + history("600006.SH", rising, last=DAY - timedelta(days=1)))   # 当天没有行情


def test_lists_the_passing_stocks_best_first_with_their_values():
    result = screen(definition(), bars(), DAY)
    assert result["checked"] == 3 and result["matched"] == 2
    first, second = result["items"]
    assert [first["symbol"], second["symbol"]] == ["600001.SH", "600002.SH"]
    assert first["close"] == 13 and first["change"] == pytest.approx(13 / 12 - 1)
    assert first["ranking"] == pytest.approx(13 / 10 - 1)
    assert first["conditions"] == [{"left": 13, "right": pytest.approx((10 + 11 + 12 + 13 + 10) / 5)}]


def test_ascending_ranking_puts_the_smallest_first_and_st_can_be_kept():
    result = screen(definition(direction="ascending"), bars(), DAY, exclude_st=False)
    assert [item["symbol"] for item in result["items"]][:1] == ["600002.SH"]
    assert "600004.SH" in {item["symbol"] for item in result["items"]} and result["checked"] == 4


def test_the_screen_agrees_with_the_backtest_rule_check():
    frame = bars()
    rule = definition()
    listed = {item["symbol"] for item in screen(rule, frame, DAY)["items"]}
    for symbol in ("600001.SH", "600002.SH", "600003.SH"):
        group = frame[frame["symbol"] == symbol].sort_values("trade_date")
        assert (rank_score(group, rule) is not None) == (symbol in listed)


def test_nothing_to_screen():
    assert screen(definition(), pd.DataFrame(), DAY) == {"checked": 0, "matched": 0, "items": []}


@pytest.fixture
def api(monkeypatch):
    from app.routes import workspace
    from app.routes.auth import get_current_user

    monkeypatch.setattr(workspace, "local_data_bounds", lambda: (date(2015, 1, 5), DAY))
    asked = {}

    class Repository:
        def get_daily_bars(self, symbols, start, end):
            asked.update(symbols=symbols, start=start, end=end)
            frame = bars()
            return frame if symbols is None else frame[frame["symbol"].isin(symbols)]

    monkeypatch.setattr(workspace, "market_repository", lambda: Repository())
    monkeypatch.setattr(workspace, "security_names", lambda: {"600001.SH": "上涨股份", "600002.SH": "慢涨股份"})
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda uid: ["600001", "600003"])
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "is_admin": False}
    return TestClient(app), asked


PAYLOAD = {"definition": {"name": "", "entry_logic": "all",
                          "entry_rules": [{"left": {"name": "close"}, "operator": "gt", "right": {"name": "sma", "window": 5}}],
                          "ranking": {"indicator": {"name": "return_1d", "window": 3}, "direction": "descending"}}}


def test_the_endpoint_screens_the_pool_or_the_whole_market(api):
    client, asked = api
    pool = client.post("/api/v1/packages/screen", json={**PAYLOAD, "scope": "pool"}).json()
    assert asked["symbols"] == ["600001.SH", "600003.SH"] and asked["end"] == DAY
    assert pool["trade_date"] == "2026-10-21" and pool["checked"] == 2 and pool["matched"] == 1
    assert pool["items"][0]["symbol"] == "600001" and pool["items"][0]["name"] == "上涨股份"
    assert pool["conditions"] == ["收盘价大于5日移动平均线"] and pool["ranking_label"] == "3日区间涨跌幅"
    assert pool["condition_indicators"] == [{"left": "close", "right": "moving_average"}]
    market = client.post("/api/v1/packages/screen", json={**PAYLOAD, "scope": "market", "limit": 1}).json()
    assert asked["symbols"] is None and market["matched"] == 2 and market["shown"] == 1


def test_bad_rules_and_an_empty_pool_are_explained(api, monkeypatch):
    from app.routes import workspace

    client, _ = api
    bad = {"definition": {**PAYLOAD["definition"], "entry_rules": [{"left": {"name": "nonsense"}, "operator": "gt", "value": 1}]}}
    assert client.post("/api/v1/packages/screen", json=bad).status_code == 422
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda uid: [])
    empty = client.post("/api/v1/packages/screen", json={**PAYLOAD, "scope": "pool"})
    assert empty.status_code == 409 and "股票池是空的" in empty.json()["detail"]
