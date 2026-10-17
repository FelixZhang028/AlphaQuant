"""AI researcher: facts read point in time from local data, the checks on the AI's answer, and the routes."""

from __future__ import annotations

from datetime import date
import json

import numpy as np
import pandas as pd
import pytest
import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.quant import platform_ai
from app.routes import agent_lab
from app.routes.auth import get_current_user
from quant_platform.ai_research.brief import BriefFormatError, REFUSAL, check_answer, check_brief, parse_json
from quant_platform.ai_research.facts import report_in_force, stock_facts
from quant_platform.ai_research.outcome import later_moves
from trading_agents.llm.base import LLMResponse

SYMBOLS = [f"{600000 + i}.SH" for i in range(40)]
DATES = pd.bdate_range("2025-01-02", periods=300)


def make_bars(days=DATES, symbols=SYMBOLS, seed=3):
    rng = np.random.default_rng(seed)
    rows = []
    for s, symbol in enumerate(symbols):
        close = 10 + s * 0.1 + np.cumsum(rng.normal(0, 0.2, len(days)))
        close = np.maximum(close, 1.0)
        for t, day in enumerate(days):
            rows.append({"symbol": symbol, "trade_date": day, "raw_close": close[t], "adjusted_close": close[t],
                         "pre_close": close[t - 1] if t else close[t], "adj_factor": 1.0,
                         "amount": 1e8 * (1 + s), "is_suspended": False, "is_st": False,
                         "list_date": pd.Timestamp("2010-01-04"), "up_limit": close[t] * 1.5, "down_limit": close[t] * 0.5})
    return pd.DataFrame(rows)


class FakeRepository:
    def __init__(self, bars, tables=None, indicators=None, reports=None):
        self.bars = bars
        self.tables = tables or {}
        self.indicators = indicators if indicators is not None else pd.DataFrame(columns=["symbol", "trade_date", "pe_ttm", "pb_mrq", "ps_ttm", "turnover_rate"])
        self.reports = reports if reports is not None else pd.DataFrame(columns=["symbol", "stat_date", "pub_date"])

    def daily_bar_bounds(self):
        return self.bars["trade_date"].min().date(), self.bars["trade_date"].max().date()

    def get_daily_bars(self, symbols=None, start_date=None, end_date=None, extras=()):
        frame = self.bars
        if symbols:
            frame = frame[frame["symbol"].isin(symbols)]
        if start_date:
            frame = frame[frame["trade_date"] >= pd.Timestamp(start_date)]
        if end_date:
            frame = frame[frame["trade_date"] <= pd.Timestamp(end_date)]
        return frame.sort_values(["trade_date", "symbol"]).reset_index(drop=True)

    def read_table(self, name):
        return self.tables.get(name, pd.DataFrame())

    def get_daily_indicators(self, symbols=None, start_date=None, end_date=None, columns=None):
        frame = self.indicators
        if symbols:
            frame = frame[frame["symbol"].isin(symbols)]
        frame = frame[(frame["trade_date"] >= pd.Timestamp(start_date)) & (frame["trade_date"] <= pd.Timestamp(end_date))]
        wanted = ["symbol", "trade_date", *(columns or [c for c in frame.columns if c not in ("symbol", "trade_date")])]
        return frame.reindex(columns=wanted).reset_index(drop=True)

    def get_fundamentals(self, symbols=None):
        return self.reports[self.reports["symbol"].isin(symbols)] if symbols else self.reports


def by_key(stock):
    return {fact.key: fact for fact in stock.facts}


def test_nothing_after_the_day_is_read():
    day = DATES[-60]
    bars = make_bars()
    later = bars.copy()
    after = later["trade_date"] > day
    later.loc[after, ["raw_close", "adjusted_close"]] *= 3  # 以后的价格完全不同
    tables = {"index_constituents": pd.DataFrame({"index_symbol": "000300.SH", "effective_date": [DATES[0], DATES[-10]],
                                                  "symbol": ["600001.SH", "600000.SH"]}),
              "corporate_actions": pd.DataFrame({"symbol": ["600000.SH"], "ex_date": [DATES[-5]], "cash_per_share": [0.5], "share_multiplier": [1.0]})}
    reports = pd.DataFrame({"symbol": ["600000.SH"], "stat_date": [DATES[-40]], "pub_date": [DATES[-20]], "roe_avg": [0.2]})
    plain = stock_facts(FakeRepository(bars), "600000.SH", day.date())
    future = stock_facts(FakeRepository(later, tables, reports=reports), "600000.SH", day.date())
    keep = lambda stock: [f for f in stock.facts if f.key not in ("indexes", "last_action")]
    assert keep(plain) == keep(future)
    facts = by_key(future)
    assert facts["indexes"].text.startswith("不在")  # 名单在这天以后才把它加进来
    assert facts["last_action"].text == "没有记录"  # 除息在这天以后
    assert any(item["group"] == "财务" for item in future.missing)  # 财报在这天以后才公告


def test_an_ex_dividend_day_is_not_a_fall():
    bars = make_bars()
    one = bars["symbol"] == "600000.SH"
    gap = one & (bars["trade_date"] >= DATES[-10])
    bars.loc[gap, "raw_close"] /= 2  # 10 送 10：原始价格减半，复权价格连续
    bars.loc[one & (bars["trade_date"] == DATES[-10]), "pre_close"] = bars.loc[one & (bars["trade_date"] == DATES[-11]), "raw_close"].iloc[0] / 2
    facts = by_key(stock_facts(FakeRepository(bars), "600000.SH"))
    adjusted = bars[one].set_index("trade_date")["adjusted_close"]
    assert facts["ret_20d"].value == pytest.approx(adjusted.iloc[-1] / adjusted.iloc[-21] - 1)
    assert facts["close"].value == pytest.approx(bars[one]["raw_close"].iloc[-1])


def test_market_position_counts_the_stocks_that_traded():
    bars = make_bars()
    leader = bars["symbol"] == "600000.SH"
    bars.loc[leader & (bars["trade_date"] > DATES[-21]), "adjusted_close"] *= 2  # 最近 20 天涨得最多
    bars.loc[(bars["symbol"] == "600039.SH") & (bars["trade_date"] == DATES[-1]), "is_suspended"] = True
    facts = by_key(stock_facts(FakeRepository(bars), "600000.SH"))
    assert facts["rank_ret_20d"].value == 1.0
    assert facts["rank_ret_20d"].text == "高于全市场 100% 的股票（共 39 只）"


def test_a_day_with_only_some_stocks_updated_is_not_compared_with_the_market():
    bars = make_bars()
    bars = bars[(bars["trade_date"] < DATES[-1]) | bars["symbol"].isin(SYMBOLS[:5])]
    stock = stock_facts(FakeRepository(bars), "600000.SH")
    assert not [f for f in stock.facts if f.group == "全市场比较"]
    reason = next(item["reason"] for item in stock.missing if item["group"] == "全市场比较")
    assert "只有 5 只" in reason and "平时约 40 只" in reason


def test_missing_parts_are_listed_instead_of_guessed():
    stock = stock_facts(FakeRepository(make_bars()), "600000.SH")
    assert {item["group"] for item in stock.missing} == {"指数成分股", "行业", "估值", "财务"}
    assert not [f for f in stock.facts if f.group in ("估值", "财务")]


def test_not_a_trading_day_uses_the_day_before():
    saturday = date(2026, 1, 3)
    days = pd.bdate_range("2025-01-02", "2026-01-09")
    stock = stock_facts(FakeRepository(make_bars(days)), "600000.SH", saturday)
    assert stock.trade_date == date(2026, 1, 2)
    assert stock.notes == ["2026-01-03 不是交易日，按前一个交易日 2026-01-02 的数据分析。"]


def test_valuation_industry_and_report():
    bars = make_bars()
    rows = [{"symbol": s, "trade_date": d, "pe_ttm": 10.0 + i + t * 0.01, "pb_mrq": 1.5, "ps_ttm": 2.0, "turnover_rate": 0.8}
            for i, s in enumerate(SYMBOLS) for t, d in enumerate(DATES)]
    exposures = pd.DataFrame({"symbol": SYMBOLS, "date": DATES[0], "industry": ["C27医药制造业"] * 10 + ["J66货币金融服务"] * 30,
                              "sector": "C"})
    reports = pd.DataFrame({"symbol": "600000.SH", "stat_date": pd.to_datetime(["2025-06-30", "2025-03-31"]),
                            "pub_date": pd.to_datetime(["2025-08-20", "2025-09-01"]),  # 旧一期迟到，不覆盖新的
                            "roe_avg": [0.08, 0.04], "asset_to_equity": [2.0, 2.0], "yoy_parent_net_profit": [-0.1, 0.3]})
    stock = stock_facts(FakeRepository(bars, {"security_exposures": exposures}, pd.DataFrame(rows), reports), "600000.SH")
    facts = by_key(stock)
    assert facts["industry"].text == "医药制造业（同行业 10 只）"
    assert facts["pe_ttm"].text == f"{10.0 + 299 * 0.01:.1f}"
    assert facts["pe_position"].text == "高于自身 100% 的交易日"
    assert facts["industry_pe_median"].text.endswith("（10 只有数据）")
    assert facts["report"].text == "2025 年半年报（2025-08-20 公告）"
    assert facts["roe_avg"].text == "8.0%" and facts["debt_ratio"].text == "50.0%" and facts["profit_growth"].text == "-10.0%"
    assert report_in_force(reports, pd.Timestamp("2026-12-01")) is None  # 一年多以前的报告不再使用


def small_stock():
    return stock_facts(FakeRepository(make_bars()), "600000.SH")


def test_check_brief_keeps_supported_points_and_drops_the_rest():
    stock = small_stock()
    facts = by_key(stock)
    ret = facts["ret_20d"].text
    data = {"tilt": "中性", "confidence": "中", "summary": f"近 20 个交易日涨跌幅 {ret}。",
            "bull_points": [{"text": f"近 20 个交易日涨跌幅 {ret}", "evidence": ["ret_20d"]},
                            {"text": "没有依据的说法", "evidence": ["made_up"]},
                            {"text": "近 20 个交易日涨了 99.9%", "evidence": ["ret_20d"]},
                            {"text": "可以考虑买入", "evidence": ["ret_20d"]}],
            "risk_points": [{"text": f"波动率 {round(facts['volatility_60d'].value * 100)}%", "evidence": ["volatility_60d"]}]}
    result = check_brief(data, stock)
    assert [p["text"] for p in result["bull_points"]] == [f"近 20 个交易日涨跌幅 {ret}"]
    assert result["bull_points"][0]["evidence"][0]["text"] == ret  # 页面显示本地的数据，不是 AI 转述的
    assert len(result["risk_points"]) == 1  # 四舍五入到整数也算对得上
    assert result["removed"] == 3 and result["summary"] and result["watch_points"] == []
    with pytest.raises(BriefFormatError):
        check_brief({"tilt": "买入"}, stock)
    assert check_brief({"tilt": "偏多", "summary": "目标价 100 元"}, stock)["summary"] == ""


def test_parse_json_and_answers():
    assert parse_json('```json\n{"tilt": "偏多"}\n```') == {"tilt": "偏多"}
    with pytest.raises(BriefFormatError):
        parse_json("没有 JSON")
    assert check_answer("建议加仓") == REFUSAL and check_answer(" 估值偏低 ") == "估值偏低"


# ---------------------------------------------------------------- routes ----


class FakeClient:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def chat(self, messages, temperature=0.2, max_tokens=2048):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMResponse(text=answer)


def good_answer(stock):
    ret = by_key(stock)["ret_20d"].text
    return ('{"tilt": "偏多", "confidence": "中", "summary": "走势平稳。", "bull_points": [{"text": "近 20 个交易日涨跌幅 %s", '
            '"evidence": ["ret_20d"]}], "risk_points": [], "watch_points": []}' % ret)


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    with database.get_conn() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (?, 'u', ?, 'h', 's', 'now')",
                         (uid, f"u{uid}@example.test"))
    repository = FakeRepository(make_bars())
    monkeypatch.setattr(agent_lab, "market_repository", lambda: repository)
    monkeypatch.setattr(agent_lab, "security_names", lambda: {"600000.SH": "测试股份"})
    monkeypatch.setattr(agent_lab, "_AGENT_ROOT", tmp_path / "agent_lab")
    for name in ("OPENROUTER_API_KEY", "FELLOWQUANT_AI_API_KEY", "FELLOWQUANT_AI_DAILY_BRIEFS"):
        monkeypatch.delenv(name, raising=False)
    app = FastAPI()
    app.include_router(agent_lab.router)
    current = {"user": {"id": 1, "is_admin": False}}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    return TestClient(app), current


def analyse(client, symbol, **extra):
    created = client.post("/api/v1/agent-lab/briefs", json={"symbol": symbol, **extra}).json()
    return client.post(f"/api/v1/agent-lab/briefs/{created['id']}/reading").json()


def use_model(monkeypatch, answers):
    monkeypatch.setenv("OPENROUTER_API_KEY", "platform-key")
    client = FakeClient(answers)
    monkeypatch.setattr(platform_ai, "model_client", lambda model: client)
    return client


def test_without_a_model_the_data_is_still_shown(api):
    client, _ = api
    assert client.get("/api/v1/agent-lab/status").json()["ai"] == {"available": False, "model": None}
    result = client.post("/api/v1/agent-lab/briefs", json={"symbol": "600000"}).json()
    assert result["brief"] is None and "还没有配置" in result["ai_note"]
    assert client.post(f"/api/v1/agent-lab/briefs/{result['id']}/reading").json()["brief"] is None
    assert result["name"] == "测试股份" and result["facts"]["facts"]
    assert client.get(f"/api/v1/agent-lab/briefs/{result['id']}").json()["facts"] == result["facts"]
    assert client.post("/api/v1/agent-lab/briefs", json={"symbol": "000001"}).status_code == 422  # 本地没有这只股票


def test_brief_retries_a_bad_answer_counts_use_and_stops_at_the_limit(api, monkeypatch):
    client, _ = api
    stock = small_stock()
    model = use_model(monkeypatch, ["不是 JSON", good_answer(stock)])
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_BRIEFS", "1")
    data = client.post("/api/v1/agent-lab/briefs", json={"symbol": "600000.SH"}).json()
    assert data["brief"] is None and data["ai_note"] == "" and not model.calls  # 第一步只整理数据
    result = client.post(f"/api/v1/agent-lab/briefs/{data['id']}/reading").json()
    assert result["brief"]["tilt"] == "偏多" and result["model"] == "deepseek-v4-pro" and len(model.calls) == 2
    assert client.post(f"/api/v1/agent-lab/briefs/{data['id']}/reading").json()["brief"] == result["brief"]
    assert len(model.calls) == 2  # 已经解读过：不再调用，也不再计数
    assert "数据表" in model.calls[0][1]["content"] and "ret_20d" in model.calls[0][1]["content"]
    status = client.get("/api/v1/agent-lab/status").json()
    assert status["usage"]["brief"] == {"limit": 1, "used": 1, "remaining": 0}
    again = analyse(client, "600000.SH")
    assert again["brief"] is None and "用完" in again["ai_note"] and again["facts"]["facts"]
    items = client.get("/api/v1/agent-lab/briefs").json()["items"]
    assert [item["tilt"] for item in items] == [None, "偏多"]


def test_a_failed_call_is_not_counted(api, monkeypatch):
    client, _ = api
    response = requests.Response()
    response.status_code = 402
    use_model(monkeypatch, [requests.HTTPError(response=response)])
    result = analyse(client, "600000.SH")
    assert result["brief"] is None and "余额不足" in result["ai_note"]
    assert client.get("/api/v1/agent-lab/status").json()["usage"]["brief"]["used"] == 0


def test_questions_use_the_saved_data_and_stay_private(api, monkeypatch):
    client, current = api
    stock = small_stock()
    model = use_model(monkeypatch, [good_answer(stock), "近 20 个交易日走势平稳。", "可以加仓"])
    brief = analyse(client, "600000.SH")
    first = client.post(f"/api/v1/agent-lab/briefs/{brief['id']}/questions", json={"message": "走势怎样？"}).json()
    assert first["questions"][-1]["answer"] == "近 20 个交易日走势平稳。"
    assert "ret_20d" in model.calls[1][1]["content"] and "倾向偏多" in model.calls[1][1]["content"]
    second = client.post(f"/api/v1/agent-lab/briefs/{brief['id']}/questions", json={"message": "要买吗？"}).json()
    assert second["questions"][-1]["answer"] == REFUSAL and second["usage"]["used"] == 2
    assert model.calls[2][3]["content"] == "走势怎样？"  # 之前的追问也带上
    assert len(client.get(f"/api/v1/agent-lab/briefs/{brief['id']}").json()["questions"]) == 2
    current["user"] = {"id": 2, "is_admin": False}
    assert client.get(f"/api/v1/agent-lab/briefs/{brief['id']}").status_code == 404
    current["user"] = {"id": 2, "is_admin": True}
    assert client.get("/api/v1/agent-lab/status").json()["usage"]["question"]["limit"] is None


def test_later_moves_compare_with_the_index():
    bars = make_bars()
    index = pd.DataFrame({"symbol": "000300.SH", "trade_date": DATES, "raw_close": np.linspace(100, 110, len(DATES))})
    repository = FakeRepository(bars, {"benchmark_bars": index})
    day = DATES[-11].date()
    moves = later_moves(repository, [("600000.SH", day), ("600001.SH", DATES[-1].date())])
    one = bars[bars["symbol"] == "600000.SH"].set_index("trade_date")["adjusted_close"]
    move = moves[("600000.SH", day)]
    assert move["end_date"] == DATES[-1].date().isoformat() and move["days"] == 10
    assert move["change"] == pytest.approx(one.iloc[-1] / one.iloc[-11] - 1)
    assert move["benchmark_change"] == pytest.approx(110 / np.linspace(100, 110, len(DATES))[-11] - 1)
    assert moves[("600001.SH", DATES[-1].date())] is None  # 分析日之后还没有行情
    assert later_moves(FakeRepository(bars), [("600000.SH", day)])[("600000.SH", day)]["benchmark_change"] is None


def test_list_shows_later_moves_and_delete_is_private(api):
    client, current = api
    day = DATES[-11].date().isoformat()
    created = client.post("/api/v1/agent-lab/briefs", json={"symbol": "600000.SH", "trade_date": day}).json()
    assert created["later"]["days"] == 10
    items = client.get("/api/v1/agent-lab/briefs").json()["items"]
    assert items[0]["later"]["change"] == pytest.approx(created["later"]["change"])
    current["user"] = {"id": 2, "is_admin": False}
    assert client.delete(f"/api/v1/agent-lab/briefs/{created['id']}").status_code == 404
    current["user"] = {"id": 1, "is_admin": False}
    assert client.delete(f"/api/v1/agent-lab/briefs/{created['id']}").status_code == 204
    assert client.get("/api/v1/agent-lab/briefs").json()["items"] == []


# ------------------------------------------------------------- decisions ----

from quant_platform.ai_research.decisions import RISK_LEVELS, backtest_facts  # noqa: E402


class FakeJev:
    model = "typesafe/jev-1.13"

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def ask(self, state, questions):
        self.calls.append((state, questions))
        if self.fail:
            raise requests.Timeout()
        answers = {}
        for name, question in questions.items():
            if question["type"] == "choice":
                answers[name] = {"type": "choice", "choice": "中性", "confidence": 0.5,
                                 "probabilities": {"偏多": 0.3, "中性": 0.5, "偏空": 0.2}}
                if "偏多" not in question["criteria"]:
                    answers[name]["probabilities"] = {key: .5 if key == "中性" else .5 / (len(question["criteria"]) - 1)
                                                       for key in question["criteria"]}
            elif question["type"] == "noul":
                answers[name] = {"type": "noul", "probability": 0.7}
            else:
                answers[name] = {"type": "score", "score": 2.4, "confidence": 0.6,
                                 "probabilities": dict(zip(question["criteria"], [0.05, 0.15, 0.4, 0.3, 0.1]))}
        return answers


def test_reading_adds_the_decision_model_odds_and_survives_its_failure(api, monkeypatch):
    client, _ = api
    stock = small_stock()
    use_model(monkeypatch, [good_answer(stock), good_answer(stock)])
    jev = FakeJev()
    monkeypatch.setattr(platform_ai, "decision_client", lambda: jev)
    result = analyse(client, "600000.SH")
    assert result["brief"]["odds"] == {"choice": "中性", "probabilities": {"偏多": 0.3, "中性": 0.5, "偏空": 0.2},
                                       "confidence": 0.5, "model": "jev-1.13"}
    state = jev.calls[0][0]
    assert state["数据"]["近 20 个交易日涨跌幅"].startswith(by_key(stock)["ret_20d"].text)  # 和页面上的数据相同
    monkeypatch.setattr(platform_ai, "decision_client", lambda: FakeJev(fail=True))
    again = analyse(client, "600000.SH")
    assert again["brief"]["tilt"] == "偏多" and again["brief"]["odds"] is None


def test_jev_alone_can_analyse_saved_data_and_reuse_it_privately(api, monkeypatch):
    client, current = api
    jev = FakeJev()
    monkeypatch.setattr(platform_ai, 'decision_client', lambda: jev)
    assert not client.get('/api/v1/agent-lab/status').json()['ai']['available']
    assert client.get('/api/v1/agent-lab/status').json()['decision']['available']
    created = client.post('/api/v1/agent-lab/briefs', json={'symbol': '600000.SH'}).json()
    result = client.post(f"/api/v1/agent-lab/briefs/{created['id']}/decision")
    assert result.status_code == 200, result.text
    assert result.json()['brief'] is None and result.json()['odds']['choice'] == '中性'
    assert client.get('/api/v1/agent-lab/status').json()['usage']['review']['used'] == 1
    again = client.post(f"/api/v1/agent-lab/briefs/{created['id']}/decision").json()
    assert again['odds'] == result.json()['odds'] and len(jev.calls) == 1
    # A failed/missing text model must not erase the independently saved decision.
    after_reading = client.post(f"/api/v1/agent-lab/briefs/{created['id']}/reading").json()
    assert after_reading['odds'] == again['odds']
    current['user'] = {'id': 2}
    assert client.post(f"/api/v1/agent-lab/briefs/{created['id']}/decision").status_code == 404


def test_independent_jev_failure_does_not_charge_or_store_a_result(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(platform_ai, 'decision_client', lambda: FakeJev(fail=True))
    created = client.post('/api/v1/agent-lab/briefs', json={'symbol': '600000.SH'}).json()
    assert client.post(f"/api/v1/agent-lab/briefs/{created['id']}/decision").status_code == 502
    assert client.get('/api/v1/agent-lab/status').json()['usage']['review']['used'] == 0
    assert client.get(f"/api/v1/agent-lab/briefs/{created['id']}").json()['odds'] is None


def test_legacy_report_requires_explicit_upgrade_and_upgrades_only_once(api, monkeypatch):
    client, _ = api
    jev = FakeJev()
    monkeypatch.setattr(platform_ai, 'decision_client', lambda: jev)
    created = client.post('/api/v1/agent-lab/briefs', json={'symbol': '600000.SH'}).json()
    legacy = {'choice': '中性', 'probabilities': {'偏多': .12, '中性': .85, '偏空': .03}, 'confidence': .6, 'model': 'jev-latest'}
    with database.get_conn() as conn:
        conn.execute('UPDATE stock_briefs SET brief=? WHERE id=?', (json.dumps({'odds': legacy}), created['id']))
    path = f"/api/v1/agent-lab/briefs/{created['id']}/decision"
    assert client.post(path).json()['odds'] == legacy and not jev.calls
    upgraded = client.post(path + '?upgrade=true')
    assert upgraded.status_code == 200, upgraded.text
    assert upgraded.json()['odds']['report_version'] == 2
    assert len(upgraded.json()['odds']['dimensions']) == 5 and len(jev.calls) == 1
    assert client.post(path + '?upgrade=true').json()['odds'] == upgraded.json()['odds']
    assert len(jev.calls) == 1
    assert client.get('/api/v1/agent-lab/status').json()['usage']['review']['used'] == 1


def test_failed_upgrade_preserves_old_report_and_refunds_quota(api, monkeypatch):
    client, _ = api
    monkeypatch.setattr(platform_ai, 'decision_client', lambda: FakeJev(fail=True))
    created = client.post('/api/v1/agent-lab/briefs', json={'symbol': '600000.SH'}).json()
    legacy = {'choice': '中性', 'probabilities': {'偏多': .12, '中性': .85, '偏空': .03}, 'confidence': .6, 'model': 'jev-latest'}
    with database.get_conn() as conn:
        conn.execute('UPDATE stock_briefs SET brief=? WHERE id=?', (json.dumps({'odds': legacy}), created['id']))
    path = f"/api/v1/agent-lab/briefs/{created['id']}"
    assert client.post(path + '/decision?upgrade=true').status_code == 502
    assert client.get(path).json()['odds'] == legacy
    assert client.get('/api/v1/agent-lab/status').json()['usage']['review']['used'] == 0


RESULT = {
    "nav_dates": ["2025-01-02"] * 243, "total_return": 23.03, "annual_return": 24.09, "max_drawdown": 6.26, "sharpe": 1.61,
    "win_rate": 57.85, "fills": 245, "closed_trades": 196, "trade_win_rate": 65.82, "average_holding_days": 62.13,
    "total_cost": 19890.13, "trades": [{"symbol": "601398"}, {"symbol": "000001"}, {"symbol": "601398"}],
    "validity_status": "WARNING", "validity_issues": [{"code": "IN_SAMPLE_ONLY", "severity": "WARNING", "message": "只做了样本内回测"}],
    "effective_config": {"market": "当前股票池", "max_positions": 10, "rebalance": "weekly", "initial_capital": 1000000.0,
                         "strategy_parameters": {"short_window": 20, "long_window": 60}},
}
BENCHMARK = {"comparable": True, "name": "沪深 300", "benchmark_return": 21.19, "excess_return": 1.84,
             "benchmark_max_drawdown": 10.49, "beta": 0.57}


def test_backtest_facts_are_the_run_s_own_numbers():
    rows = {row.key: row.text for row in backtest_facts({"from_date": "2025-01-01", "to_date": "2025-12-31"}, RESULT, BENCHMARK)}
    assert rows["period"] == "2025-01-01 至 2025-12-31（243 个交易日）"
    assert rows["max_drawdown"] == "6.26%" and rows["rebalance"] == "每周" and rows["parameters"] == "2 个"
    assert rows["cost"] == "1.99%" and rows["stocks"] == "2 只" and rows["excess_return"] == "1.84%"
    assert rows["validity"] == "有警告" and rows["issue_1"] == "只做了样本内回测"
    assert "excess_return" not in {r.key for r in backtest_facts({}, RESULT, {"comparable": False})}


def test_backtest_review_is_saved_counted_once_and_private(tmp_path, monkeypatch):
    import json as _json
    from app.routes import backtests
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    with database.get_conn() as conn:
        for uid in (1, 2):
            conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (?, 'u', ?, 'h', 's', 'now')",
                         (uid, f"u{uid}@example.test"))
        conn.execute("INSERT INTO backtests (id, user_id, strategy, market, from_date, to_date, status, result, created_at) "
                     "VALUES (7, 1, 'a_share_momentum', '当前股票池', '2025-01-01', '2025-12-31', '完成', ?, 'now')", (_json.dumps(RESULT),))
    monkeypatch.setattr(backtests, "benchmark_comparison", lambda directory: BENCHMARK)
    monkeypatch.setattr(backtests, "with_run_evidence", lambda result: result)  # 测试里没有运行目录
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_REVIEWS", "1")
    app = FastAPI()
    app.include_router(backtests.router)
    current = {"user": {"id": 1, "is_admin": False}}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    client = TestClient(app)

    monkeypatch.setattr(platform_ai, "decision_client", lambda: None)
    assert client.get("/api/v1/backtests/7/ai-review").json()["available"] is False
    assert client.post("/api/v1/backtests/7/ai-review").status_code == 422
    jev = FakeJev()
    monkeypatch.setattr(platform_ai, "decision_client", lambda: jev)
    review = client.post("/api/v1/backtests/7/ai-review").json()["review"]
    assert review["risk"]["level"] == RISK_LEVELS[2] and review["overfit"]["probability"] == 0.7
    assert review["model"] == "jev-1.13" and any(f["text"] == "只做了样本内回测" for f in review["facts"])
    assert set(jev.calls[0][1]) == {"risk", "overfit"}  # 两个问题一次请求
    assert "收益与风险 · 最大回撤：6.26%" in jev.calls[0][0]["回测数据"]  # 发给模型的就是页面上的这些行
    again = client.post("/api/v1/backtests/7/ai-review").json()
    assert again["review"]["risk"] == review["risk"] and len(jev.calls) == 1 and again["usage"]["used"] == 1
    assert client.get("/api/v1/backtests/7/ai-review").json()["review"]["overfit"]["probability"] == 0.7
    current["user"] = {"id": 2, "is_admin": False}
    assert client.get("/api/v1/backtests/7/ai-review").json()["review"] is None
    assert client.post("/api/v1/backtests/7/ai-review").status_code == 404
