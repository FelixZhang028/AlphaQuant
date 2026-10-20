"""AI 研究员的结构化报告：不用模型，只用当天以前的本地数据。"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from quant_platform.ai_research import report
from quant_platform.ai_research.facts import stock_facts
from test_ai_research import DATES, SYMBOLS, FakeRepository, analyse, api, make_bars  # noqa: F401 - api 是夹具

ADVICE = ("买入", "卖出", "加仓", "减仓", "建议", "目标价", "止损")


def quarter_reports(symbol="600000.SH"):
    """2023Q1 ~ 2025Q2 十份财报：营收每年涨 10%，利润增长一路下降，负债率一路上升。"""

    rows = []
    stats = pd.to_datetime(["2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31", "2024-03-31", "2024-06-30",
                            "2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30"])
    for i, stat in enumerate(stats):
        rows.append({"symbol": symbol, "stat_date": stat, "pub_date": stat + pd.Timedelta(days=30),
                     "revenue": 100.0 * (1.1 ** (stat.year - 2023)) * (stat.month / 3),
                     "yoy_parent_net_profit": 0.5 - i * 0.1, "gross_margin": 0.3, "net_margin": 0.1,
                     "roe_avg": 0.02 * (stat.month / 3), "asset_to_equity": 2.0 + i * 0.2, "total_shares": 1e9})
    return pd.DataFrame(rows)


def test_financial_trend_is_point_in_time_and_says_how_ratios_moved():
    trend = report.financial_trend(quarter_reports(), pd.Timestamp("2025-06-01"))   # 2025 半年报还没公布
    rows = trend["rows"]
    assert len(rows) == 8 and rows[-1]["period"] == "2025一季报" and rows[0]["period"] == "2023半年报"
    assert abs(rows[-1]["revenue_yoy"] - 0.1) < 1e-9                               # 和去年同一季度比
    assert trend["trends"]["profit_yoy"] == "连续下降" and trend["trends"]["debt_ratio"] == "连续上升"
    assert trend["trends"]["gross_margin"] == "基本持平"
    assert "roe" not in trend["trends"]                                             # 年初至今累计的，不比走向
    assert report.financial_trend(quarter_reports(), pd.Timestamp("2023-01-01")) is None


def test_trend_words():
    assert report._trend([1, 2, 3, 4]) == "连续上升"
    assert report._trend([4, 3, 2, 1]) == "连续下降"
    assert report._trend([1, 3, 2, 4]) == "有升有降"
    assert report._trend([1, None, None]) == "数据不足"
    assert report._trend([2, 2, 2]) == "基本持平"


def full_repository():
    bars = make_bars()
    bars.loc[bars["symbol"] == "600000.SH", "is_st"] = bars.loc[bars["symbol"] == "600000.SH", "trade_date"] >= DATES[-30]
    indicators = pd.DataFrame([{"symbol": s, "trade_date": d, "pe_ttm": 10.0 + i + t * 0.01, "pb_mrq": 1.5 + i * 0.01,
                                "ps_ttm": 2.0, "turnover_rate": 0.8} for i, s in enumerate(SYMBOLS) for t, d in enumerate(DATES)])
    exposures = pd.DataFrame({"symbol": SYMBOLS, "date": DATES[0], "industry": ["C27医药制造业"] * 12 + ["J66货币金融服务"] * 28, "sector": "C"})
    reports = pd.concat([quarter_reports(s).assign(total_shares=1e9 * (1 + i)) for i, s in enumerate(SYMBOLS[:12])])
    actions = pd.DataFrame({"symbol": ["600000.SH"], "ex_date": [DATES[-40]], "cash_per_share": [0.25], "share_multiplier": [1.0]})
    first, second = DATES[-100].date(), DATES[-50].date()
    constituents = pd.DataFrame({"index_symbol": "000300.SH", "effective_date": [first] * 2 + [second],
                                 "symbol": ["600001.SH", "600002.SH", "600000.SH"]})
    tables = {"security_exposures": exposures, "corporate_actions": actions, "index_constituents": constituents,
              "security_master": pd.DataFrame({"symbol": SYMBOLS, "name": [f"股票{i}" for i in range(40)]})}
    return FakeRepository(bars, tables, indicators, reports)


def test_a_full_report_from_local_data():
    stock = stock_facts(full_repository(), "600000.SH", name="测试股份")
    built = stock.report
    assert built["version"] == report.REPORT_VERSION
    titles = [item["title"] for item in built["summaries"]]
    assert titles[:3] == ["基本信息", "价格走势", "成交"] and "财务" in titles and "同行对比" in titles
    text = " ".join(item["text"] for item in built["summaries"])
    assert not any(word in text for word in ADVICE)                                 # 只描述，不给建议
    checks = {item["key"]: item for item in built["checks"]}
    assert checks["st"]["state"] == "warn" and checks["liquidity"]["state"] == "ok"
    assert checks["profit_drop"]["state"] == "warn"                                 # 最新一份净利润同比 -40%
    assert all(item["rule"] for item in built["checks"])                            # 每一条都写明规则
    peers = built["peers"]
    assert peers["count"] == 12 and len(peers["rows"]) == 7 and any(row["self"] for row in peers["rows"])
    assert set(peers["ranks"]) >= {"market_cap", "pe"} and peers["median"]["pe"] is not None
    assert built["financial_trend"]["rows"][-1]["period"] == "2025半年报"
    charts = built["charts"]
    assert len(charts["prices"]) == report.CHART_DAYS and charts["prices"][-1][0] == DATES[-1].date().isoformat()
    kinds = {event["kind"] for event in charts["events"]}
    assert {"action", "index", "st"} <= kinds
    assert any(event["text"] == "调入沪深300" for event in charts["events"])
    assert charts["valuation"]["bands"]["pe_ttm"]["share"] > 0.99                # 市盈率一直在涨，现在接近最高
    factors = built["factors"]
    assert factors and factors["items"] and all(0 <= item["market_share"] <= 1 for item in factors["items"] if item["market_share"] is not None)


def test_a_partly_updated_day_has_no_factor_profile():
    bars = make_bars()
    bars = bars[~((bars["trade_date"] == DATES[-1]) & (bars["symbol"] != "600000.SH"))]
    stock = stock_facts(FakeRepository(bars), "600000.SH")
    assert "unavailable" in stock.report["factors"]


def test_a_factor_profile_still_being_computed_is_filled_in_later(monkeypatch):
    repository = FakeRepository(make_bars())
    monkeypatch.setattr(report, "COMPUTE_IN_BACKGROUND", True)
    started = []
    monkeypatch.setattr(report.threading, "Thread", lambda target, **kwargs: type("T", (), {"start": lambda self: started.append(target)})())
    stock = stock_facts(repository, "600000.SH")
    assert stock.report["factors"]["pending"] is True and len(started) == 1
    assert not any(item["key"] == "factors" for item in stock.report["summaries"])
    assert report.fill_pending_factors(repository, stock.report, "600000.SH") is False   # 还没算完
    started[0]()                                                                        # 后台算完
    assert report.fill_pending_factors(repository, stock.report, "600000.SH") is True
    assert stock.report["factors"]["items"] and any(item["key"] == "factors" for item in stock.report["summaries"])


def test_compare_two_analyses():
    before = {"facts": [{"key": "close", "label": "收盘价", "text": "10.00 元", "value": 10.0},
                        {"key": "pe_ttm", "label": "市盈率", "text": "12.0", "value": 12.0}]}
    after = {"facts": [{"key": "close", "label": "收盘价", "text": "11.00 元", "value": 11.0},
                       {"key": "pe_ttm", "label": "市盈率", "text": "12.0", "value": 12.0}]}
    assert report.compare_facts(before, after) == [{"key": "close", "label": "收盘价", "before": "10.00 元", "after": "11.00 元", "delta": 1.0}]


def test_the_api_returns_the_report_and_the_change_since_last_time(api):
    client, _ = api
    first = analyse(client, "600000", trade_date=DATES[-30].date().isoformat())
    assert first["facts"]["report"]["summaries"] and first["previous"] is None
    second = analyse(client, "600000")
    assert second["previous"]["id"] == first["id"]
    assert any(change["key"] == "close" for change in second["previous"]["changes"])
    reopened = client.get(f"/api/v1/agent-lab/briefs/{second['id']}").json()
    assert reopened["facts"]["report"] == second["facts"]["report"]


def test_the_report_is_plain_json():
    stock = stock_facts(full_repository(), "600000.SH")
    text = json.dumps(stock.to_dict(), allow_nan=False)          # 没有 NaN，也没有 numpy 类型
    assert '"self": true' in text
    assert report.clean({"a": float("nan"), "b": np.float64(1.5), "c": [np.bool_(True), float("inf")]}) == {"a": None, "b": 1.5, "c": [True, None]}


def test_values_for_the_same_day_on_older_data_are_used_while_data_keeps_changing(tmp_path, monkeypatch):
    repository = FakeRepository(make_bars())
    repository.root = tmp_path / "market"
    repository.root.mkdir()
    (repository.root / "bars.parquet").write_bytes(b"v1")
    day = DATES[-1]
    first = report.ensure_cross_section(repository, day, background=False)
    assert first is not None and list((tmp_path / "factor_profiles").glob("*.parquet"))
    report._FACTOR_CACHE.clear()
    (repository.root / "reports.parquet").write_bytes(b"new")                       # 数据又变了
    assert report.known_cross_section(repository, day, exact=True) is None           # 严格要求时需要重算
    assert report.known_cross_section(repository, day, exact=False) is not None     # 显示时先用同一天已经算好的
