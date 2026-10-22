"""条件选股的 AI 解读和“过去表现如何”：只用本地数据、要点要有依据、不给股票排名、同一天不重复扣次数。"""

import json
from datetime import date, timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from quant_platform.ai_research.brief import BriefFormatError
from quant_platform.ai_research.screen_brief import check_screen_brief, screen_facts, screen_messages

DAY = date(2026, 10, 21)


def bars(symbol, start, step, days=80):
    rows = []
    for i in range(days):
        close = start + step * i
        rows.append({"symbol": symbol, "trade_date": pd.Timestamp(DAY - timedelta(days=days - 1 - i)),
                     "adjusted_close": close, "raw_close": close, "pre_close": close - step, "amount": 2e8})
    return rows


HISTORY = pd.DataFrame(bars("600001.SH", 10, 0.1) + bars("600002.SH", 20, -0.05))
LATEST = pd.DataFrame([
    {"symbol": "600001.SH", "pe_ttm": 12.5, "pb_mrq": 1.2, "turnover_rate": 0.8, "industry": "银行"},
    {"symbol": "600002.SH", "pe_ttm": None, "pb_mrq": 3.4, "turnover_rate": 5.1, "industry": "I65软件和信息技术服务业"},
])
ITEMS = [{"symbol": "600001.SH", "name": "甲银行", "close": 17.9, "change": 0.0056},
         {"symbol": "600002.SH", "name": "乙软件", "close": 16.05, "change": -0.0031}]


def facts():
    return screen_facts(ITEMS, HISTORY, LATEST, day=DAY, matched=57, scope="market",
                        conditions="收盘价大于60日移动平均线", ranking="按20日区间涨跌幅从高到低排序")


def test_the_facts_table_has_each_stock_and_the_group():
    stock = facts()
    keys = stock.by_key()
    assert keys["600001.industry"].text == "银行" and keys["600001.pe_ttm"].text == "12.5"
    assert keys["600002.pe_ttm"].text == "本地没有" and keys["600002.rank"].text.startswith("第 2 名")
    assert keys["600001.ret_20d"].text == f"{(17.9 / 15.9 - 1) * 100:+.2f}%"
    assert keys["all.matched"].text == "全市场里共 57 只符合条件" and keys["all.shown"].text == "排序前 2 只"
    assert keys["all.industry"].text == "软件和信息技术服务业 1 只、银行 1 只"      # 去掉分类代码
    assert keys["all.pe_ttm"].text.startswith("中位数 12.5") and "1 只有数据" in keys["all.pe_ttm"].text
    prompt = screen_messages(stock)
    assert "不要给股票排名" in prompt[0]["content"] and "600001.ret_20d" in prompt[1]["content"]


def test_points_need_evidence_matching_numbers_and_no_orders_or_ranking_words():
    stock = facts()
    answer = {
        "summary": "这组股票里有 2 只，行业是银行和软件。",
        "common_points": [
            {"text": "两只近 20 日平均成交额都是 2.00 亿元", "evidence": ["600001.amount_20d", "600002.amount_20d"]},
            {"text": "市盈率 99 倍", "evidence": ["600001.pe_ttm"]},             # 数字对不上：去掉
            {"text": "甲银行估值偏低", "evidence": []},                            # 没有依据：去掉
        ],
        "outlier_points": [{"text": "乙软件换手率 5.10%", "evidence": ["600002.turnover"]}],
        "risk_points": [{"text": "甲银行走势看涨，可以买入", "evidence": ["600001.ret_20d"]}],   # 买卖、方向：去掉
        "check_points": [{"text": "乙软件没有市盈率，可以核查最新财报", "evidence": ["600002.pe_ttm"]}],
    }
    checked = check_screen_brief(answer, stock)
    assert checked["summary"] == "这组股票里有 2 只，行业是银行和软件。"   # “2 只”是只数，允许
    assert [p["text"] for p in checked["common_points"]] == ["两只近 20 日平均成交额都是 2.00 亿元"]
    assert checked["risk_points"] == [] and checked["removed"] == 3
    assert checked["outlier_points"][0]["evidence"][0]["key"] == "600002.turnover"
    with pytest.raises(BriefFormatError):
        check_screen_brief({"summary": "没有要点"}, stock)
    too_many = check_screen_brief({"summary": "有 31 只", "common_points": []}, stock)
    assert too_many["summary"] == ""                                        # 31 只超过解读的只数：不是允许的只数


# --------------------------------------------------------------------------- #
# 接口
# --------------------------------------------------------------------------- #


class Model:
    label = "test-model"


class Client:
    def __init__(self, answers):
        self.answers, self.calls = list(answers), []

    def chat(self, messages, **_):
        self.calls.append(messages)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return type("Reply", (), {"text": answer})()


GOOD = json.dumps({"summary": "解读了 2 只股票。", "common_points": [
    {"text": "近 20 日平均成交额 2.00 亿元", "evidence": ["600001.amount_20d"]}], "risk_points": []}, ensure_ascii=False)
PAYLOAD = {"definition": {"name": "", "entry_logic": "all",
                          "entry_rules": [{"left": {"name": "close"}, "operator": "gt", "value": 0}],
                          "ranking": {"indicator": {"name": "return_1d", "window": 20}, "direction": "descending"}},
           "scope": "market"}


@pytest.fixture
def api(tmp_path, monkeypatch):
    from app import database
    from app.quant import platform_ai
    from app.routes import workspace
    from app.routes.auth import get_current_user

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    with database.get_conn() as conn:
        conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (1, 'u', 'u@example.test', 'h', 's', 'now')")
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_SCREENS", "1")
    monkeypatch.setattr(workspace, "local_data_bounds", lambda: (date(2015, 1, 5), DAY))
    result = {"checked": 2, "matched": 57, "items": [dict(item) for item in ITEMS]}
    monkeypatch.setattr(workspace, "_run_screen", lambda body, user: (workspace._screen_rule(body.definition), DAY, result))

    class Repository:
        def get_daily_bars(self, symbols, start, end, extras=()):
            return LATEST if extras else HISTORY

    monkeypatch.setattr(workspace, "market_repository", lambda: Repository())
    monkeypatch.setattr(workspace, "security_names", lambda: {})
    client = Client([GOOD])
    monkeypatch.setattr(platform_ai, "platform_model", lambda: Model())
    monkeypatch.setattr(platform_ai, "model_client", lambda model: client)
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "is_admin": False}
    return TestClient(app), client, result


def test_the_brief_is_charged_once_and_reused_the_same_day(api):
    http, client, _ = api
    first = http.post("/api/v1/packages/screen/brief", json=PAYLOAD)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["cached"] is False and body["stocks"] == 2 and body["model"] == "test-model"
    assert body["brief"]["common_points"][0]["text"] == "近 20 日平均成交额 2.00 亿元"
    assert body["usage"]["used"] == 1 and len(client.calls) == 1
    again = http.post("/api/v1/packages/screen/brief", json=PAYLOAD).json()
    assert again["cached"] is True and again["brief"] == body["brief"] and len(client.calls) == 1   # 不再调用、不再计数
    other = {**PAYLOAD, "scope": "pool"}                                     # 换了范围：是另一组结果
    refused = http.post("/api/v1/packages/screen/brief", json=other)
    assert refused.status_code == 429 and "用完" in refused.json()["detail"]   # 免费 1 次用完、积分为 0


def test_a_failed_model_call_is_not_counted_and_an_empty_result_is_explained(api, monkeypatch):
    import requests

    http, client, result = api
    client.answers = [requests.Timeout()]
    failed = http.post("/api/v1/packages/screen/brief", json=PAYLOAD)
    assert failed.status_code == 502 and "不计入次数" in failed.json()["detail"]
    status = http.post("/api/v1/packages/screen/brief", json=PAYLOAD)
    assert status.status_code == 502                                        # 没有答案了；之前那次没扣
    result["items"] = []
    empty = http.post("/api/v1/packages/screen/brief", json=PAYLOAD)
    assert empty.status_code == 409 and "没有股票" in empty.json()["detail"]


def test_the_history_backtest_uses_the_same_rules_and_is_saved_like_any_backtest(api, monkeypatch):
    from app.routes import workspace

    http, _, _ = api
    seen = {}

    def run(user, package, **options):
        seen.update(package=package, **options)
        return {"id": 7, "run_id": "r", "status": "完成", "summary": {"total_return": 5.0}}

    monkeypatch.setattr(workspace, "_run_backtest", run)
    made = http.post("/api/v1/packages/screen/history", json={"definition": PAYLOAD["definition"], "market": "000300.SH"})
    assert made.status_code == 201 and made.json()["id"] == 7
    assert seen["market"] == "000300.SH" and seen["end"] == DAY and seen["start"] == DAY - timedelta(days=365)
    assert seen["package"].top_n == 5 and seen["package"].rebalance == "weekly" and seen["package"].name == "条件选股"
    assert seen["reference"] == "" and seen["package_id"] is None
