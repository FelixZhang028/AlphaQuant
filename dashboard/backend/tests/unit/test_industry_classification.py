"""Industry classification history and the neutralization that uses it."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes import workspace
from app.routes.auth import get_current_user
from quant_platform.application import data_jobs
from quant_platform.application.data_service import DataCenterService
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.fundamentals import FUNDAMENTALS_TABLE, MISSING_FUNDAMENTALS_MESSAGE, STORED_COLUMNS
from quant_platform.data.industry import (
    EXPOSURES_TABLE,
    MISSING_INDUSTRY_MESSAGE,
    SNAPSHOTS_TABLE,
    industry_on,
    new_change_points,
    normalize_baostock_industry,
)
from quant_platform.data.industry_backfill import BaoStockIndustryBackfill
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.factors.registry import default_registry

BANK, LIQUOR, BATTERY, SOFTWARE = "J66货币金融服务", "C15酒、饮料和精制茶制造业", "C38电气机械和器材制造业", "I65软件和信息技术服务业"


def vendor_snapshot(update, industries):
    return pd.DataFrame([{"updateDate": update, "code": code, "code_name": code, "industry": industry, "industryClassification": "证监会行业分类"}
                         for code, industry in industries.items()])


def test_a_snapshot_keeps_classified_stocks_and_dates_them_by_when_it_was_current():
    rows = normalize_baostock_industry(vendor_snapshot("2025-06-23", {"sz.000001": BANK, "sh.600519": LIQUOR, "sh.600001": "", "sz.000003": " "}))
    assert rows[["symbol", "industry", "sector"]].values.tolist() == [["000001.SZ", BANK, "J"], ["600519.SH", LIQUOR, "C"]]
    # 问的是 6 月 30 日，厂商说这份分类是 6 月 23 日的：按 6 月 23 日记。
    assert rows["date"].unique().tolist() == [pd.Timestamp("2025-06-23")] and rows["source"].eq("baostock").all()
    assert normalize_baostock_industry(pd.DataFrame()).empty


def test_only_first_classifications_and_changes_are_kept():
    first = normalize_baostock_industry(vendor_snapshot("2025-03-31", {"sz.000001": BANK, "sz.300750": BATTERY}))
    assert len(new_change_points(pd.DataFrame(), first)) == 2
    second = normalize_baostock_industry(vendor_snapshot("2025-06-30", {"sz.000001": BANK, "sz.300750": SOFTWARE, "sh.600519": LIQUOR}))
    kept = new_change_points(first, second)
    assert sorted(kept["symbol"]) == ["300750.SZ", "600519.SH"]            # 没变的平安银行不再存一行
    stored = pd.concat([first, kept], ignore_index=True)
    # 补一张更早的快照：只有当时就不同的才是新信息。
    older = normalize_baostock_industry(vendor_snapshot("2024-12-31", {"sz.000001": BANK, "sz.300750": LIQUOR}))
    assert new_change_points(stored, older)["symbol"].tolist() == ["000001.SZ", "300750.SZ"]
    back = normalize_baostock_industry(vendor_snapshot("2025-09-30", {"sz.300750": BATTERY}))
    assert new_change_points(stored, back)["industry"].tolist() == [BATTERY]   # 改回原来的行业也是一次变化


def changes_frame():
    return pd.DataFrame([
        {"symbol": "A", "date": pd.Timestamp("2025-03-31"), "industry": BANK, "sector": "J"},
        {"symbol": "B", "date": pd.Timestamp("2025-03-31"), "industry": BATTERY, "sector": "C"},
        {"symbol": "B", "date": pd.Timestamp("2025-06-30"), "industry": SOFTWARE, "sector": "I"},
    ])


def test_industry_on_a_day_is_what_was_known_then():
    days = pd.DataFrame({"symbol": ["B", "B", "B", "A", "Z", "B"],
                         "date": pd.to_datetime(["2025-05-06", "2025-06-30", "2025-08-01", "2025-08-01", "2025-08-01", "2025-01-10"])})
    known = industry_on(days, changes_frame())
    assert known.tolist()[:4] == [BATTERY, SOFTWARE, SOFTWARE, BANK]
    assert pd.isna(known.tolist()[4])                                      # 从来没有分类的股票
    assert known.tolist()[5] == BATTERY                                    # 第一条记录之前：用最早的一次分类
    assert industry_on(days, changes_frame(), level="sector").tolist()[:2] == ["C", "I"]
    assert industry_on(days, pd.DataFrame()).isna().all()
    with pytest.raises(ValueError, match="行业层级"):
        industry_on(days, changes_frame(), level="subindustry")


# --------------------------------------------------------------------------- #
# Downloading
# --------------------------------------------------------------------------- #

TODAY = date(2025, 8, 20)


class Vendor:
    def __init__(self, failing=()):
        self.requests, self.failing, self.logins = [], set(failing), 0

    def login(self):
        self.logins += 1

    def close(self):
        pass

    def get_industry_snapshot(self, day=None):
        self.requests.append(day)
        if day in self.failing:
            raise DataUnavailableError("no answer")
        battery = BATTERY if day < date(2025, 6, 1) else SOFTWARE
        return vendor_snapshot(day.isoformat(), {"sz.000001": BANK, "sz.300750": battery, "sh.600519": LIQUOR, "sh.600001": ""})


def test_history_is_one_snapshot_per_quarter_end_plus_today_stored_as_change_points(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    vendor, seen = Vendor(), []
    result = BaoStockIndustryBackfill(repo, vendor, today=TODAY).backfill(
        date(2024, 11, 1), date(2030, 1, 1), progress=lambda stage, done, total: seen.append((stage, done, total)))
    assert vendor.requests == [date(2024, 12, 31), date(2025, 3, 31), date(2025, 6, 30), TODAY] and vendor.logins == 1
    assert result == {"snapshots": 4, "changes": 4, "failed": {}} and seen[-1] == ("industry", 4, 4)
    stored = repo.read_table(EXPOSURES_TABLE).sort_values(["symbol", "date"])
    assert stored[["symbol", "date", "industry"]].values.tolist() == [
        ["000001.SZ", pd.Timestamp("2024-12-31"), BANK],
        ["300750.SZ", pd.Timestamp("2024-12-31"), BATTERY],
        ["300750.SZ", pd.Timestamp("2025-06-30"), SOFTWARE],
        ["600519.SH", pd.Timestamp("2024-12-31"), LIQUOR],
    ]
    assert len(repo.read_table(SNAPSHOTS_TABLE)) == 4

    # 再运行：季度末的快照不再取，只重新取最新的一张；多出的一天也只多取一张。
    again = Vendor()
    BaoStockIndustryBackfill(repo, again, today=TODAY).backfill(date(2024, 11, 1), date(2030, 1, 1))
    assert again.requests == [TODAY]
    later = Vendor()
    BaoStockIndustryBackfill(repo, later, today=date(2025, 10, 9)).backfill(date(2024, 11, 1), date(2030, 1, 1))
    assert later.requests == [date(2025, 9, 30), date(2025, 10, 9)]


def test_a_failed_snapshot_is_reported_and_asked_again_next_time(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    result = BaoStockIndustryBackfill(repo, Vendor(failing={date(2025, 3, 31)}), today=TODAY).backfill(date(2025, 1, 1), date(2030, 1, 1))
    assert result["snapshots"] == 2 and list(result["failed"]) == ["2025-03-31"]
    retry = Vendor()
    BaoStockIndustryBackfill(repo, retry, today=TODAY).backfill(date(2025, 1, 1), date(2030, 1, 1))
    assert retry.requests == [date(2025, 3, 31), TODAY]


def test_status_and_the_background_job(tmp_path, monkeypatch):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    days = pd.bdate_range("2025-01-02", periods=5)
    repo.save_table("daily_bars", pd.concat([pd.DataFrame({"symbol": symbol, "trade_date": days, "raw_open": 1.0, "raw_close": 1.0})
                                             for symbol in ("000001.SZ", "300750.SZ", "688001.SH")], ignore_index=True))
    service = SimpleNamespace(repository=repo)
    assert DataCenterService.industry_status(service) == {"symbols": 0, "missing_symbols": 3, "snapshots": 0, "start_date": None, "end_date": None}
    BaoStockIndustryBackfill(repo, Vendor(), today=TODAY).backfill(date(2025, 1, 1), date(2030, 1, 1))
    assert DataCenterService.industry_status(service) == {
        "symbols": 2, "missing_symbols": 1, "snapshots": 3, "start_date": "2025-03-31", "end_date": "2025-08-20"}

    calls = []
    job_service = SimpleNamespace(app={"app": {"runtime_dir": str(tmp_path)}},
                                  backfill_industry=lambda start, end, progress=None: calls.append((start, end)) or {"failed": {}, "snapshots": 3})
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: job_service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2015-01-05", "end_date": "2025-08-20", "datasets": ["industry"]}
    assert data_jobs.attempt(folder, job) == 0 and calls == [(date(2015, 1, 5), date(2025, 8, 20))]


# --------------------------------------------------------------------------- #
# Neutralization
# --------------------------------------------------------------------------- #

DAYS = pd.bdate_range("2025-04-01", periods=45)
INDUSTRIES = [BANK, LIQUOR, BATTERY]
SYMBOLS = [f"{number:06d}.SZ" for number in range(1, 16)]


def market(tmp_path, classified=SYMBOLS):
    """Fifteen stocks in three industries; price levels, and so momentum, differ by industry."""

    rng = np.random.default_rng(5)
    repo = ParquetMarketDataRepository(tmp_path / "market")
    frames = []
    for index, symbol in enumerate(SYMBOLS):
        drift = 0.004 * (index % 3 - 1)
        close = 10 * np.cumprod(1 + drift + rng.normal(0, 0.01, len(DAYS)))
        frames.append(pd.DataFrame({"symbol": symbol, "trade_date": DAYS, "raw_open": close, "raw_high": close * 1.01, "raw_low": close * 0.99,
                                    "raw_close": close, "pre_close": close, "volume": 1e5, "amount": 1e6, "adjusted_close": close,
                                    "adj_factor": 1.0, "quality_status": "OK", "source": "baostock"}))
    repo.save_table("daily_bars", pd.concat(frames, ignore_index=True))
    repo.save_table(EXPOSURES_TABLE, pd.DataFrame([
        {"symbol": symbol, "date": pd.Timestamp("2025-03-31"), "industry": INDUSTRIES[SYMBOLS.index(symbol) % 3], "sector": "X", "source": "baostock"}
        for symbol in classified]))
    return repo


def momentum():
    return default_registry().get("momentum_20")


def test_industry_neutral_values_have_no_industry_average_left(tmp_path):
    repo = market(tmp_path)
    evaluator = FactorEvaluator(repo)
    bars = repo.get_daily_bars()
    values = momentum().compute(bars)
    values = values[values["date"] >= DAYS[25]]
    raw_means = values.assign(industry=values["symbol"].map(lambda s: INDUSTRIES[SYMBOLS.index(s) % 3])).groupby(["date", "industry"])["value"].mean()
    assert raw_means.abs().max() > 0.02                                    # 原始因子值里有明显的行业差别
    neutral, notes = evaluator._neutralized(values, bars, "industry")
    means = neutral.assign(industry=neutral["symbol"].map(lambda s: INDUSTRIES[SYMBOLS.index(s) % 3])).groupby(["date", "industry"])["value"].mean()
    assert means.abs().max() < 1e-12 and notes == [] and len(neutral) == len(values)
    report = evaluator.evaluate(momentum(), DAYS[25].date(), DAYS[-2].date(), horizon=1, n_groups=5, neutralization="industry")
    assert report.daily_ic is not None and not any("中性化" in note for note in report.notes)


def test_stocks_without_a_classification_are_left_out_and_counted(tmp_path):
    repo = market(tmp_path, classified=SYMBOLS[:12])
    bars = repo.get_daily_bars()
    values = momentum().compute(bars)
    values = values[values["date"] == DAYS[30]]
    neutral, notes = FactorEvaluator(repo)._neutralized(values, bars, "industry")
    assert sorted(neutral["symbol"]) == SYMBOLS[:12]
    assert notes == ["3 个样本缺少当时的行业分类或市值，没有参与中性化（共 15 个样本）"]


def test_neutralization_says_what_is_missing_or_why_it_cannot_be_done(tmp_path):
    repo = market(tmp_path)
    evaluator = FactorEvaluator(repo)
    span = dict(start_date=DAYS[25].date(), end_date=DAYS[-2].date(), horizon=1, n_groups=5)
    with pytest.raises(ValueError) as error:
        evaluator.evaluate(momentum(), **span, neutralization="size")
    assert str(error.value) == MISSING_FUNDAMENTALS_MESSAGE
    with pytest.raises(ValueError, match="股票数量太少，做不了中性化"):
        evaluator.evaluate(momentum(), **span, symbols=SYMBOLS[:4], neutralization="industry")
    bare = ParquetMarketDataRepository(tmp_path / "bare")
    bare.save_table("daily_bars", repo.get_daily_bars())
    with pytest.raises(ValueError) as error:
        FactorEvaluator(bare).evaluate(momentum(), **span, neutralization="industry")
    assert str(error.value) == MISSING_INDUSTRY_MESSAGE
    with pytest.raises(ValueError, match="未知中性化方式"):
        evaluator.evaluate(momentum(), **span, neutralization="sector")


def test_size_neutralization_uses_the_market_cap_known_on_each_day(tmp_path):
    repo = market(tmp_path)
    reports = []
    for index, symbol in enumerate(SYMBOLS):
        row = {column: np.nan for column in STORED_COLUMNS}
        row.update(symbol=symbol, stat_date=pd.Timestamp("2024-12-31"), pub_date=pd.Timestamp("2025-03-20"), total_shares=1e8 * (1 + index), source="baostock")
        reports.append(row)
    repo.save_table(FUNDAMENTALS_TABLE, pd.DataFrame(reports, columns=STORED_COLUMNS))
    evaluator = FactorEvaluator(repo)
    bars = repo.get_daily_bars()
    values = momentum().compute(bars)
    values = values[values["date"] >= DAYS[25]]
    neutral, notes = evaluator._neutralized(values, bars, "both")
    assert notes == [] and len(neutral) == len(values)
    # 残差和对数市值不再相关。
    day = neutral[neutral["date"] == DAYS[30]].set_index("symbol")["value"]
    cap = np.log(bars[bars["trade_date"] == DAYS[30]].set_index("symbol")["raw_close"] * pd.Series({s: 1e8 * (1 + i) for i, s in enumerate(SYMBOLS)}))
    assert abs(np.corrcoef(day.reindex(SYMBOLS), cap.reindex(SYMBOLS))[0, 1]) < 1e-8


def test_the_route_accepts_the_four_neutralization_choices(monkeypatch):
    asked = []
    evaluator = SimpleNamespace(evaluate=lambda factor, start, end, **options: asked.append(options["neutralization"]) or (_ for _ in ()).throw(ValueError("stop")))
    monkeypatch.setattr(workspace, "build_factor_evaluator", lambda: evaluator)
    monkeypatch.setattr(workspace, "build_factor_registry", lambda user: default_registry())
    monkeypatch.setattr(workspace, "_factor_symbols", lambda user: None)
    monkeypatch.setattr(workspace, "_clamped_range", lambda start, end: (date(2025, 1, 1), date(2025, 6, 30)))
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1}
    client = TestClient(app)
    for choice in ("none", "industry", "size", "both"):
        assert client.post("/api/v1/factors/evaluate", json={"factor_name": "momentum_20", "neutralization": choice}).status_code == 422
    assert asked == ["none", "industry", "size", "both"]
    assert client.post("/api/v1/factors/evaluate", json={"factor_name": "momentum_20"}).status_code == 422 and asked[-1] == "none"
    bad = client.post("/api/v1/factors/evaluate", json={"factor_name": "momentum_20", "neutralization": "sector"})
    assert bad.status_code == 422 and len(asked) == 5
