"""功能台首页：指数卡片、涨跌分布、行业涨跌、我的股票池、最近的研究、新手任务、财报季，一个请求拿到。"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.quant import home
from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.ai_research import screen
from test_ai_research import DATES, SYMBOLS, FakeRepository, make_bars

DAY = DATES[-1]


def market():
    bars = make_bars()
    last = bars["trade_date"] == DAY
    # 第 1 只今天涨停，第 2 只跌停，第 3 只停牌，第 4 只是 ST
    for i, (column, factor) in enumerate([("up_limit", 1.1), ("down_limit", 0.9)]):
        row = last & (bars["symbol"] == SYMBOLS[i])
        bars.loc[row, "pre_close"] = 10.0
        bars.loc[row, "raw_close"] = 10.0 * factor
        bars.loc[row, column] = 10.0 * factor
    bars.loc[last & (bars["symbol"] == SYMBOLS[2]), "is_suspended"] = True
    bars.loc[last & (bars["symbol"] == SYMBOLS[3]), "is_st"] = True
    exposures = pd.DataFrame({"symbol": SYMBOLS, "date": DATES[0], "sector": "C",
                              "industry": ["J66货币金融服务"] * 10 + ["C27医药制造业"] * 10 + ["C36汽车制造业"] * 20})
    index_days = DATES[-70:]
    benchmarks = pd.DataFrame([{"symbol": symbol, "trade_date": day, "raw_close": 3000.0 + t, "pre_close": 2999.0 + t}
                               for symbol in ("000300.SH", "000001.SH", "000016.SH") for t, day in enumerate(index_days)])
    reports = pd.DataFrame({"symbol": SYMBOLS[:3], "stat_date": pd.Timestamp("2026-09-30"),
                            "pub_date": pd.to_datetime(["2026-10-15", "2026-10-18", "2026-10-25"])})
    return FakeRepository(bars, {"security_exposures": exposures, "benchmark_bars": benchmarks}, reports=reports)


def test_index_cards_follow_the_home_order_with_the_change_and_three_months_of_closes():
    cards = home.indexes(market())
    assert [card["name"] for card in cards] == ["上证指数", "沪深 300"]           # 本地没有的指数不显示；上证50 不在首页
    assert cards[0]["close"] == 3069.0 and cards[0]["change"] == pytest.approx(3069 / 3068 - 1, abs=1e-4)
    assert len(cards[0]["series"]) == home.SPARK_DAYS and cards[0]["date"] == DAY.date().isoformat()


def test_breadth_industries_and_the_pool_come_from_the_day():
    day, table = screen.build_snapshot(market(), {SYMBOLS[0]: "第一股份"})
    counts = home.breadth(table, day)
    assert counts["total"] == 39 and counts["suspended"] == 1
    assert counts["limit_up"] == 1 and counts["limit_down"] == 1
    assert counts["up"] + counts["down"] + counts["flat"] == 39
    sectors = home.industries(table, day)
    assert sectors["count"] == 3 and len(sectors["up"]) == 3
    assert [s["name"] for s in sectors["up"]] == [s["name"] for s in reversed(sectors["down"])]
    assert sectors["up"][0]["change"] >= sectors["up"][-1]["change"]
    rows = home.pool(table, ["600000", "600002", "688999"], {"688999.SH": "还没上市"})
    assert rows[0]["name"] == "第一股份" and rows[0]["change"] == pytest.approx(0.1)
    assert rows[1]["suspended"] is True
    assert rows[2] == {**rows[2], "name": "还没上市", "close": None, "missing": True}


def test_report_seasons_are_the_periods_being_published_now():
    repository = market()
    q3 = home.report_seasons(repository, 5000, date(2026, 10, 20))
    assert q3 == [{"period": "2026三季报", "deadline": "2026-10-31", "published": 2, "listed": 5000, "days_left": 11}]
    april = home.report_seasons(repository, 5000, date(2027, 4, 10))
    assert [season["period"] for season in april] == ["2026年报", "2027一季报"]   # 四月年报和一季报一起公布
    assert home.report_seasons(repository, 5000, date(2026, 12, 5)) == []


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    with database.get_conn() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (?, 'u', ?, 'h', 's', 'now')",
                         (uid, f"u{uid}@example.test"))
        conn.execute("INSERT INTO backtests (id, user_id, strategy, market, from_date, to_date, status, result, created_at) VALUES "
                     "(5, 1, '动量', 'A股', '2025-01-01', '2025-12-31', '完成', '{\"total_return\": 12.5, \"max_drawdown\": 8.1}', '2026-10-01T00:00:00'), "
                     "(6, 2, '别人的', 'A股', '2025-01-01', '2025-12-31', '完成', '{}', '2026-10-02T00:00:00')")
        conn.execute("INSERT INTO stock_briefs (id, user_id, symbol, name, trade_date, facts, created_at) VALUES "
                     "('b1', 1, '600000.SH', '第一股份', '2026-10-19', '{}', '2026-10-03T00:00:00')")
        conn.execute("INSERT INTO ai_chats (id, user_id, title, turns, created_at, updated_at) VALUES "
                     "('c1', 1, '银行股的估值', '[]', '2026-10-04T00:00:00', '2026-10-04T00:00:00')")
    repository = market()
    monkeypatch.setattr(home, "market_repository", lambda: repository)
    monkeypatch.setattr(home, "security_names", lambda: {SYMBOLS[0]: "第一股份"})
    monkeypatch.setattr(workspace, "_load_universe_symbols", lambda user_id: ["600000", "600001"])
    monkeypatch.setattr(workspace, "_data_jobs", lambda: type("Jobs", (), {"records": lambda self: []})())
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "name": "u", "email": "u1@example.test", "is_admin": False}
    return TestClient(app)


def test_the_home_page_is_one_request_with_only_my_research(client):
    body = client.get("/api/v1/home").json()
    assert [card["name"] for card in body["indexes"]] == ["上证指数", "沪深 300"]
    assert body["breadth"]["limit_up"] == 1 and [row["symbol"] for row in body["pool"]] == ["600000", "600001"]
    assert [item["kind"] for item in body["recent"]] == ["chat", "brief", "backtest"]           # 从新到旧，只有自己的
    assert body["recent"][2]["detail"] == "总收益 +12.50% · 最大回撤 8.10%" and body["recent"][2]["context"] == {"run": 5}
    assert body["counts"] == {"strategies": 0, "backtests": 1, "briefs": 1, "chats": 1}
    assert [step["done"] for step in body["steps"]] == [False, False, True, True]
    assert set(body["daily"]) == {"enabled", "time", "state", "text", "data_date"} and body["daily"]["data_date"] == DAY.date().isoformat()
    assert body["ai"]["available"] is False and body["ai"]["usage"]["chat"]["used"] == 0
