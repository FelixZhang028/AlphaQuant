"""股票查询里的财务：历期财报从新到旧、和去年同期比、每个空着的数字都说明原因。"""

from datetime import date

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant.stock_financials import stock_financials
from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.data.fundamentals import FUNDAMENTALS_TABLE
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

TODAY = date(2026, 10, 20)


def report(stat, pub, **values):
    row = {"symbol": "600519.SH", "stat_date": pd.Timestamp(stat), "pub_date": pd.Timestamp(pub) if pub else pd.NaT,
           "revenue": None, "net_profit": 100e8, "yoy_net_profit": 0.05, "yoy_parent_net_profit": None,
           "gross_margin": 0.9, "net_margin": 0.5, "roe_avg": 0.2, "asset_to_equity": 1.25, "eps_ttm": 60.0,
           "current_ratio": 4.0, "quick_ratio": 3.0, "total_shares": 12.5e8, "float_shares": 12.5e8}
    row.update(values)
    return row


def frame(*rows):
    return pd.DataFrame(list(rows))


def test_reports_are_listed_newest_first_and_set_against_the_same_period_last_year():
    reports = frame(
        report("2025-06-30", "2025-08-10", revenue=800e8, gross_margin=0.91, roe_avg=0.18),
        report("2025-09-30", "2025-10-30"),
        report("2026-03-31", "2026-04-25"),
        report("2026-06-30", "2026-08-15", revenue=920e8, gross_margin=0.89, roe_avg=0.18, yoy_parent_net_profit=-0.02),
        report("2026-09-30", "2026-10-28", revenue=1300e8),                   # 还没有公布（公布日期在今天之后）
    )
    result = stock_financials(reports, today=TODAY)
    assert [row["period"] for row in result["rows"]] == ["2026半年报", "2026一季报", "2025三季报", "2025半年报"]
    assert result["periods"] == 4 and result["first_period"] == "2025半年报" and result["last_period"] == "2026半年报"
    latest = result["latest"]
    assert latest["revenue_yoy"] == pytest.approx(920 / 800 - 1)
    assert latest["profit_yoy"] == -0.02                                          # 优先用归母净利润同比
    assert latest["debt_ratio"] == pytest.approx(0.2)                              # 1 - 1 / 权益乘数
    assert latest["last_year"] == "2025半年报"
    assert latest["changes"]["gross_margin"] == pytest.approx(-0.02) and latest["changes"]["roe"] == pytest.approx(0)
    # 报告期已经结束、还没到最晚公布日期：告诉读者下一份什么时候会有。
    assert result["next_report"] == {"period": "2026三季报", "deadline": "2026-10-31"}


def test_every_blank_says_why():
    reports = frame(
        report("2026-03-31", "2026-04-25", gross_margin=None),
        report("2026-06-30", "2026-08-15", revenue=500e8, asset_to_equity=None),
    )
    rows = {row["period"]: row for row in stock_financials(reports, today=TODAY)["rows"]}
    q1, h1 = rows["2026一季报"], rows["2026半年报"]
    assert "一季报、三季报" in q1["missing"]["revenue"] and q1["missing"]["revenue_yoy"] == "这一期没有营收，算不出同比"
    assert "金融公司" in q1["missing"]["gross_margin"]
    assert h1["missing"]["revenue_yoy"] == "本地没有去年同期的营收，算不出同比"
    assert "权益乘数" in h1["missing"]["debt_ratio"] and "revenue" not in h1["missing"]
    assert stock_financials(reports, today=TODAY)["latest"]["changes"]["gross_margin"] is None


def test_periods_the_vendor_has_no_report_for_are_named():
    reports = frame(report("2025-09-30", None), report("2025-12-31", None))
    result = stock_financials(reports, today=TODAY)
    assert result["rows"] == [] and result["latest"] is None and result["empty_periods"] == ["2025年报", "2025三季报"]
    assert stock_financials(pd.DataFrame(columns=["symbol", "stat_date", "pub_date"]), today=TODAY)["periods"] == 0


@pytest.fixture
def client(tmp_path, monkeypatch):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("trade_calendar", pd.DataFrame({"cal_date": pd.date_range("2026-01-05", "2026-01-09"), "is_open": 1}))
    repository.save_table("security_master", pd.DataFrame({"symbol": ["600519.SH", "000001.SZ"], "name": ["贵州茅台", "平安银行"]}))
    repository.save_table("daily_bars", pd.DataFrame({"symbol": ["600519.SH"], "trade_date": [pd.Timestamp("2026-01-05")],
                                                      "quality_status": ["OK"], "raw_close": [10.0]}))
    repository.save_table(FUNDAMENTALS_TABLE, frame(report("2026-06-30", "2026-08-15", revenue=920e8)))
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "is_admin": False}
    monkeypatch.setattr(workspace, "market_repository", lambda: repository)
    with TestClient(app) as test_client:
        yield test_client


def test_the_route_returns_one_stock_and_rejects_unknown_ones(client):
    body = client.get("/api/v1/data-center/market/600519/financials").json()
    assert body["symbol"] == "600519" and body["name"] == "贵州茅台" and body["rows"][0]["revenue"] == 920e8
    body = client.get("/api/v1/data-center/market/000001.SZ/financials").json()      # 有名称、没有财报
    assert body["name"] == "平安银行" and body["rows"] == []
    assert client.get("/api/v1/data-center/market/123456/financials").status_code == 404
