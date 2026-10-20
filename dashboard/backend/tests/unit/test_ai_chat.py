"""AI 问答：模型先选要查的本地数据，后端查好，模型只根据查到的数据回答；对话按人保存。"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from app import database
from app.quant import ai_chat
from quant_platform.ai_research import screen
from quant_platform.ai_research.brief import REFUSAL
from quant_platform.ai_research.chat import MAX_LOOKUPS, answer_messages, context_text, parse_plan, plan_messages
from test_ai_research import DATES, SYMBOLS, FakeRepository, api, make_bars, use_model  # noqa: F401 - api 是 fixture

DAY = DATES[-1]


def market():
    bars = make_bars()
    bars.loc[(bars["symbol"] == SYMBOLS[1]) & (bars["trade_date"] == DAY), "is_st"] = True
    indicators = pd.DataFrame([{"symbol": s, "trade_date": DAY, "pe_ttm": -5.0 if i == 2 else 10.0 + i, "pb_mrq": 1.0 + i / 10,
                                "ps_ttm": 2.0, "turnover_rate": 1.0} for i, s in enumerate(SYMBOLS)])
    exposures = pd.DataFrame({"symbol": SYMBOLS, "date": DATES[0], "sector": "C",
                              "industry": ["C15酒、饮料和精制茶制造业"] * 10 + ["J66货币金融服务"] * 30})
    constituents = pd.DataFrame({"index_symbol": "000016.SH", "effective_date": DATES[0], "symbol": SYMBOLS[:5]})
    reports = pd.DataFrame({"symbol": SYMBOLS, "stat_date": pd.Timestamp("2025-09-30"), "pub_date": DATES[-30],
                            "roe_avg": [0.01 * i for i in range(40)], "gross_margin": 0.5, "net_margin": 0.2,
                            "yoy_net_profit": 0.1, "asset_to_equity": 2.0, "total_shares": 1e9})
    return FakeRepository(bars, {"security_exposures": exposures, "index_constituents": constituents}, indicators, reports)


# ------------------------------------------------------------ the plan ----


def test_the_plan_keeps_only_known_lookups_with_valid_parameters():
    plan = json.dumps({"lookups": [
        {"type": "stock", "symbol": "600000"}, {"type": "financials", "symbol": "茅台"}, {"type": "stock", "symbol": "600001"},
        {"type": "stock", "symbol": "600002"},                                   # 单只股票最多 3 个
        {"type": "delete_everything"}, {"type": "rank", "metric": "price_target"},  # 不认识的种类、指标
        {"type": "rank", "metric": "pe_ttm", "order": "low", "scope": "sz50", "limit": 99},
    ]}, ensure_ascii=False)
    lookups = parse_plan(plan)
    assert [item["type"] for item in lookups] == ["stock", "financials", "stock", "rank"] and len(lookups) <= MAX_LOOKUPS
    assert lookups[-1] == {"type": "rank", "metric": "pe_ttm", "order": "low", "scope": "sz50", "industry": "", "industry_of": "", "limit": 20}
    assert parse_plan("我不知道") == [] and parse_plan('{"lookups": "no"}') == []
    twice = parse_plan('{"lookups": [{"type": "data_status"}, {"type": "data_status"}, {"type": "compare", "symbols": ["600000"]}]}')
    assert twice == [{"type": "data_status"}]                                   # 重复的只查一次；比较至少两只


def test_what_the_user_is_looking_at_goes_into_both_prompts():
    line = context_text({"page": "股票查询", "stock": "贵州茅台（600519）", "backtest": 3})
    assert line == "用户正在看：页面：股票查询；正在看的股票：贵州茅台（600519）；正在看的回测：编号 3"
    history = [{"question": "上一个问题", "answer": "上一个回答"}]
    plan = plan_messages("它的毛利率呢", history, line)
    assert plan[1]["content"] == "上一个问题" and line in plan[-1]["content"]
    answer = answer_messages("它的毛利率呢", [], [{"title": "表", "as_of": "2026-10-19", "columns": ["a"], "rows": [["1"]], "notes": ["n"]}], line)
    assert "【表】数据截至 2026-10-19" in answer[-1]["content"] and "说明：n" in answer[-1]["content"]
    assert context_text({}) == ""


# ------------------------------------------------------- local lookups ----


def test_the_market_table_ranks_within_a_scope_and_says_what_was_left_out():
    day, table = screen.build_snapshot(market(), {SYMBOLS[0]: "第一股份"})
    assert day == DAY and len(table) == 40 and table.at[SYMBOLS[0], "name"] == "第一股份"
    assert table.at[SYMBOLS[0], "industry"] == "酒、饮料和精制茶制造业" and table.at[SYMBOLS[0], "indexes"] == ["上证50"]
    assert table.at[SYMBOLS[3], "debt_ratio"] == pytest.approx(0.5)
    assert table.at[SYMBOLS[3], "market_cap"] == pytest.approx(table.at[SYMBOLS[3], "close"] * 1e9)
    block = screen.rank(table, day, "pe_ttm", order="low", scope="sz50", limit=3)
    # 上证50 里：第 2 只是 ST，第 3 只市盈率为负，都不排
    assert [row[2] for row in block["rows"]] == ["600000", "600003", "600004"] and block["count"] == 3
    assert any("为负的 1 只" in note for note in block["notes"]) and block["notes"][-1] == screen.RANK_NOTE
    banks = screen.rank(table, day, "roe", industry="银行", limit=2)
    assert banks["rows"][0][2] == "600039" and "货币金融服务" in banks["title"]
    same = screen.rank(table, day, "roe", industry_of=SYMBOLS[0], limit=20)
    assert len(same["rows"]) == 9 and "报告期" in same["columns"]                 # 同行业 10 只，去掉 1 只 ST
    with pytest.raises(ValueError, match="相近的行业"):
        screen.rank(table, day, "roe", industry="航天")
    with pytest.raises(ValueError, match="不能按"):
        screen.rank(table, day, "price_target")
    both = screen.compare(table, day, [SYMBOLS[0], "999999.SH"], ["roe", "pb_mrq"])
    assert both["rows"][0][:4] == ["第一股份", "600000", "0.0%", "1.00"] and "999999" in both["notes"][0]


def test_stock_names_and_codes_are_resolved():
    names = {"600519.SH": "贵州茅台", "000001.SZ": "平安银行", "600036.SH": "招商银行"}
    assert ai_chat.resolve_symbol("600519", names) == ("600519.SH", "贵州茅台")
    assert ai_chat.resolve_symbol("茅台", names) == ("600519.SH", "贵州茅台")
    with pytest.raises(ai_chat.NotAnswerable, match="好几只"):
        ai_chat.resolve_symbol("银行", names)
    with pytest.raises(ai_chat.NotAnswerable, match="没有找到"):
        ai_chat.resolve_symbol("不存在", names)


def test_the_deepest_fall_and_the_best_and_worst_months():
    dates = ["2025-01-02", "2025-01-15", "2025-02-03", "2025-02-20", "2025-03-03", "2025-03-31"]
    equity = [100, 110, 88, 99, 112, 120]
    window = ai_chat.drawdown_window(dates, equity)
    assert window == {"peak": "2025-01-15", "low": "2025-02-03", "depth": pytest.approx(-0.2), "recovered": "2025-03-03", "days": 1}
    months = ai_chat.monthly_returns(dates, equity)
    assert list(months.round(4)) == [0.1, round(99 / 110 - 1, 4), round(120 / 99 - 1, 4)]
    assert ai_chat.drawdown_window(dates, [1, 2, 3, 4, 5, 6]) is None and ai_chat.drawdown_window([], []) is None


# --------------------------------------------------------------- routes ----


@pytest.fixture
def chat_api(api, monkeypatch):
    client, current = api
    repository = market()
    monkeypatch.setattr(ai_chat, "market_repository", lambda: repository)
    monkeypatch.setattr(ai_chat, "security_names", lambda: {SYMBOLS[0]: "第一股份", SYMBOLS[3]: "第四股份"})
    monkeypatch.delenv("FELLOWQUANT_AI_DAILY_CHATS", raising=False)
    with database.get_conn() as conn:
        conn.execute("INSERT INTO backtests (id, user_id, strategy, market, from_date, to_date, status, result, created_at) "
                     "VALUES (7, 2, 's', 'm', '2025-01-01', '2025-12-31', '完成', '{}', 'now')")
    return client, current


def ask(client, message, **extra):
    return client.post("/api/v1/agent-lab/chats", json={"message": message, **extra})


def test_without_a_model_there_is_no_chat(chat_api):
    client, _ = chat_api
    response = ask(client, "茅台怎么样")
    assert response.status_code == 422 and "没有配置文本模型" in response.json()["detail"]


def test_a_question_looks_up_local_data_answers_from_it_and_is_saved(chat_api, monkeypatch):
    client, _ = chat_api
    model = use_model(monkeypatch, [
        '{"lookups": [{"type": "rank", "metric": "roe", "industry": "银行", "limit": 3}, {"type": "stock", "symbol": "这只"}]}',
        "按净资产收益率排在前面的是第四十只。",
        '{"lookups": []}', "市净率是股价除以每股净资产。",
    ])
    first = ask(client, "银行里净资产收益率最高的是哪些？", context={"page": "股票查询", "symbol": "600000", "backtest": "7"})
    assert first.status_code == 200
    chat = first.json()["chat"]
    turn = chat["turns"][0]
    assert turn["answer"] == "按净资产收益率排在前面的是第四十只。" and chat["title"] == "银行里净资产收益率最高的是哪些？"
    assert [block["kind"] for block in turn["data"]] == ["rank", "stock"]
    assert turn["data"][0]["rows"][0][2] == "600039" and "没有找到" in turn["data"][1]["error"]
    # 别人的回测不会放进对话；看的股票换成了名称
    assert turn["context"] == {"page": "股票查询", "stock": "第一股份（600000）"}
    sent = model.calls[1][-1]["content"]
    assert "【全市场 · 货币金融服务净资产收益率（年初至报告期）最高的 3 只】" in sent and "第一股份（600000）" in sent
    second = ask(client, "什么是市净率？", chat_id=chat["id"])
    assert len(second.json()["chat"]["turns"]) == 2 and second.json()["chat"]["turns"][1]["data"] == []
    assert model.calls[2][1]["content"] == "银行里净资产收益率最高的是哪些？"      # 带上了上一轮
    assert second.json()["usage"]["used"] == 2
    listed = client.get("/api/v1/agent-lab/chats").json()["items"]
    assert listed == [{"id": chat["id"], "title": chat["title"], "updated_at": listed[0]["updated_at"], "turns": 2}]


def test_trading_advice_is_replaced_and_failures_are_not_counted(chat_api, monkeypatch):
    client, _ = chat_api
    import requests

    use_model(monkeypatch, ['{"lookups": []}', "建议现在买入。", requests.Timeout("slow")])
    assert ask(client, "要不要买？").json()["chat"]["turns"][0]["answer"] == REFUSAL
    failed = ask(client, "再问一次")
    assert failed.status_code == 422 and "不计入次数" in failed.json()["detail"]
    assert client.get("/api/v1/agent-lab/status").json()["usage"]["chat"]["used"] == 1


def test_chats_are_private_and_limited_per_day(chat_api, monkeypatch):
    client, current = chat_api
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_CHATS", "1")
    use_model(monkeypatch, ['{"lookups": []}', "回答。"])
    chat_id = ask(client, "第一个问题").json()["chat"]["id"]
    limited = ask(client, "第二个问题", chat_id=chat_id)
    assert limited.status_code == 429 and "AI 问答" in limited.json()["detail"]
    current["user"] = {"id": 2, "is_admin": False}
    assert client.get(f"/api/v1/agent-lab/chats/{chat_id}").status_code == 404
    assert client.delete(f"/api/v1/agent-lab/chats/{chat_id}").status_code == 404
    assert ask(client, "接着问", chat_id=chat_id).status_code in (404, 422)
    assert client.get("/api/v1/agent-lab/chats").json()["items"] == []
    current["user"] = {"id": 1, "is_admin": False}
    assert client.delete(f"/api/v1/agent-lab/chats/{chat_id}").status_code == 204
    assert client.get("/api/v1/agent-lab/chats").json()["items"] == []


def test_chats_are_exported_and_deleted_with_the_account(chat_api, monkeypatch):
    from app.quant import accounts

    client, _ = chat_api
    use_model(monkeypatch, ['{"lookups": []}', "回答。"])
    ask(client, "导出时要有这个问题")
    monkeypatch.setattr(accounts, "_run_directories", lambda user_id: [])
    exported = accounts.export_account(1)["tables"]["ai_chats"]
    assert exported[0]["turns"][0]["question"] == "导出时要有这个问题"      # JSON 文本还原成对象
    accounts.delete_account(1)
    with database.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM ai_chats").fetchone()[0] == 0
