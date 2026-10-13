"""Daily valuation and turnover: stored beside the bars, filled in for history, used by factors."""
from datetime import date
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quant_platform.application import data_jobs
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.baostock_backfill import BaoStockRangeBackfill
from quant_platform.data.indicator_backfill import BaoStockIndicatorBackfill, missing_ranges
from quant_platform.data.indicators import (
    INDICATOR_COLUMNS,
    INDICATOR_TABLE,
    MISSING_INDICATORS_MESSAGE,
    indicator_columns,
    normalize_baostock_indicators,
    split_daily_indicators,
)
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository
from quant_platform.factors.evaluation import FactorEvaluator
from quant_platform.factors.registry import default_registry
from quant_platform.strategies.factor_composite import FactorCompositeStrategy

DAYS = pd.bdate_range("2024-12-23", periods=30)
CODES = {"000001.SZ": "sz.000001", "600519.SH": "sh.600519", "300750.SZ": "sz.300750"}


def vendor_rows(symbol, days, pe=10.0, turn=1.5):
    """What BaoStock returns for a raw daily request that includes the indicator fields."""

    return pd.DataFrame([{
        "date": day.date().isoformat(), "code": CODES[symbol], "open": "10.0", "high": "10.6", "low": "9.8", "close": "10.2",
        "preclose": "10.0", "volume": "100000", "amount": "1020000", "adjustflag": "3", "tradestatus": "1", "pctChg": "2.0", "isST": "0",
        "peTTM": str(pe + index * 0.1), "pbMRQ": "1.25", "psTTM": "2.5", "pcfNcfTTM": "-8.0", "turn": str(turn),
    } for index, day in enumerate(days)])


class Vendor:
    """A BaoStock stand-in that records what was requested."""

    def __init__(self, failing=()):
        self.requests, self.failing, self.logins = [], set(failing), 0

    def login(self):
        self.logins += 1

    def close(self):
        pass

    def get_security_metadata(self, symbols):
        return pd.DataFrame({"symbol": symbols, "code_name": symbols, "ipoDate": "2010-01-04", "outDate": "", "status": "1"})

    def _days(self, start, end):
        return [day for day in DAYS if start <= day.date() <= end]

    def get_history_range(self, symbol, start_date, end_date, *, adjustflag):
        rows = vendor_rows(symbol, self._days(start_date, end_date))
        return rows if adjustflag == "3" else rows.drop(columns=["peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "turn"])

    def get_indicator_range(self, symbol, start_date, end_date):
        self.requests.append((symbol, start_date, end_date))
        if symbol in self.failing:
            raise DataUnavailableError("no answer")
        return vendor_rows(symbol, self._days(start_date, end_date))[["date", "code", "peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "turn"]]


def bars(symbol, days):
    return pd.DataFrame({"symbol": symbol, "trade_date": days, "raw_open": 10.0, "raw_high": 10.6, "raw_low": 9.8, "raw_close": 10.2,
                         "pre_close": 10.0, "volume": 100000.0, "amount": 1020000.0, "adjusted_close": 10.2, "adj_factor": 1.0,
                         "quality_status": "OK", "source": "baostock"})


@pytest.fixture
def repo(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("daily_bars", pd.concat([bars("000001.SZ", DAYS), bars("600519.SH", DAYS[5:25])], ignore_index=True))
    return repository


# --------------------------------------------------------------------------- #
# Normalizing and storing
# --------------------------------------------------------------------------- #


def test_vendor_rows_become_indicator_rows_and_unavailable_values_stay_missing():
    raw = vendor_rows("000001.SZ", DAYS[:4])
    raw.loc[1, ["peTTM", "pbMRQ"]] = ["0.000000", ""]          # 没有盈利数据时厂商给 0；空串是没有值
    raw.loc[2, ["peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "turn"]] = ["0", "0", "0", "0", ""]   # 停牌日：什么都没有
    result = normalize_baostock_indicators(raw)
    assert list(result.columns) == ["symbol", "trade_date", *INDICATOR_COLUMNS, "source", "ingested_at"]
    assert result["symbol"].unique().tolist() == ["000001.SZ"] and result["source"].eq("baostock").all()
    assert result["trade_date"].tolist() == [DAYS[0], DAYS[1], DAYS[3]]           # 五项都没有的那一天不存
    assert np.isnan(result.loc[1, "pe_ttm"]) and np.isnan(result.loc[1, "pb_mrq"])
    assert result.loc[0, INDICATOR_COLUMNS].tolist() == [10.0, 1.25, 2.5, -8.0, 1.5]  # 负的市现率是真实值，保留
    assert normalize_baostock_indicators(raw.drop(columns=["peTTM", "pbMRQ", "psTTM", "pcfNcfTTM", "turn"])).empty


def test_indicators_that_travel_with_fresh_bars_are_split_off_before_saving():
    fresh = bars("000001.SZ", DAYS[:3]).assign(pe_ttm=[10.0, np.nan, 12.0], turnover_rate=[1.0, np.nan, 2.0])
    kept, indicators = split_daily_indicators(fresh, "baostock")
    assert not set(INDICATOR_COLUMNS) & set(kept.columns) and len(kept) == 3
    assert indicators["trade_date"].tolist() == [DAYS[0], DAYS[2]] and list(indicators.columns[:2]) == ["symbol", "trade_date"]
    assert indicators["pb_mrq"].isna().all()
    untouched, nothing = split_daily_indicators(bars("000001.SZ", DAYS[:3]), "akshare")
    assert nothing.empty and list(untouched.columns) == list(bars("000001.SZ", DAYS[:3]).columns)


def test_a_range_update_saves_indicators_beside_the_bars_without_changing_the_bar_table(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    BaoStockRangeBackfill(RawDataRepository(tmp_path / "raw"), repository, Vendor()).backfill(
        ["000001.SZ", "600519.SH"], DAYS[0].date(), DAYS[9].date())
    stored_bars = repository.get_daily_bars()
    assert len(stored_bars) == 20 and not set(INDICATOR_COLUMNS) & set(stored_bars.columns)
    indicators = repository.get_daily_indicators()
    assert len(indicators) == 20 and indicators.loc[0, "pe_ttm"] == 10.0
    assert sorted(path.name for path in (repository.root / INDICATOR_TABLE).iterdir()) == ["year=2024", "year=2025"]


def test_bars_can_be_read_with_indicator_columns_attached(repo):
    repo.save_table(INDICATOR_TABLE, normalize_baostock_indicators(vendor_rows("000001.SZ", DAYS[:10])))
    plain = repo.get_daily_bars(["000001.SZ"])
    joined = repo.get_daily_bars(["000001.SZ"], extras=["pe_ttm", "turnover_rate", "raw_close"])
    assert list(joined.columns) == [*plain.columns, "pe_ttm", "turnover_rate"] and len(joined) == len(plain) == 30
    assert joined["pe_ttm"].notna().sum() == 10 and joined.loc[0, "turnover_rate"] == 1.5
    # 没有指标的股票：行情照常返回，指标是空值。
    other = repo.get_daily_bars(["600519.SH"], extras=["pe_ttm"])
    assert len(other) == 20 and other["pe_ttm"].isna().all()
    window = repo.get_daily_indicators(["000001.SZ"], DAYS[2].date(), DAYS[4].date(), columns=["pb_mrq"])
    assert list(window.columns) == ["symbol", "trade_date", "pb_mrq"] and len(window) == 3
    assert indicator_columns(["raw_close", "turnover_rate", "pe_ttm"]) == ["pe_ttm", "turnover_rate"]


def test_indicator_spans_follow_the_stored_files(repo):
    assert repo.daily_indicator_spans().empty
    repo.save_table(INDICATOR_TABLE, normalize_baostock_indicators(vendor_rows("000001.SZ", DAYS[3:8])))
    spans = repo.daily_indicator_spans()
    assert spans.loc["000001.SZ"].tolist() == [5, DAYS[3], DAYS[7]]
    repo.save_table(INDICATOR_TABLE, normalize_baostock_indicators(vendor_rows("000001.SZ", DAYS[8:10])))
    assert repo.daily_indicator_spans().loc["000001.SZ"].tolist() == [7, DAYS[3], DAYS[9]]


# --------------------------------------------------------------------------- #
# Filling in history
# --------------------------------------------------------------------------- #


def test_only_the_dates_without_indicators_are_requested():
    first, last = date(2025, 1, 1), date(2025, 3, 31)
    assert missing_ranges(first, last, None, None) == [(first, last)]
    assert missing_ranges(first, last, date(2025, 1, 1), date(2025, 3, 31)) == []
    assert missing_ranges(first, last, date(2025, 2, 1), date(2025, 2, 28)) == [(first, date(2025, 1, 31)), (date(2025, 3, 1), last)]
    assert missing_ranges(first, last, date(2024, 6, 1), date(2025, 2, 28)) == [(date(2025, 3, 1), last)]
    assert missing_ranges(first, last, date(2023, 1, 1), date(2023, 6, 1)) == [(first, last)]
    assert missing_ranges(last, first, None, None) == []


def test_history_backfill_covers_each_stocks_own_bars_and_a_second_run_asks_for_nothing(repo):
    vendor, seen = Vendor(), []
    result = BaoStockIndicatorBackfill(repo, vendor).backfill(
        date(2020, 1, 1), date(2030, 1, 1), progress=lambda stage, done, total: seen.append((stage, done, total)))
    assert result == {"symbols": 2, "updated": 2, "rows": 50, "failed": {}}
    # 每只股票只请求它自己有行情的那一段，一次请求。
    assert vendor.requests == [("000001.SZ", DAYS[0].date(), DAYS[-1].date()), ("600519.SH", DAYS[5].date(), DAYS[24].date())]
    assert vendor.logins == 1 and seen[0] == ("daily_indicators", 0, 2) and seen[-1] == ("daily_indicators", 2, 2)
    assert len(repo.get_daily_bars()) == 50 and not set(INDICATOR_COLUMNS) & set(repo.get_daily_bars().columns)

    again = Vendor()
    assert BaoStockIndicatorBackfill(repo, again).backfill(date(2020, 1, 1), date(2030, 1, 1))["symbols"] == 0
    assert again.requests == [] and again.logins == 0

    # 行情又多了几天：只补新增的那几天。
    repo.save_table("daily_bars", bars("600519.SH", DAYS[25:28]))
    more = Vendor()
    BaoStockIndicatorBackfill(repo, more).backfill(date(2020, 1, 1), date(2030, 1, 1))
    assert more.requests == [("600519.SH", DAYS[24].date() + pd.Timedelta(days=1), DAYS[27].date())]


def test_one_failing_stock_does_not_stop_the_rest_and_is_retried_next_time(repo):
    result = BaoStockIndicatorBackfill(repo, Vendor(failing={"000001.SZ"})).backfill(date(2020, 1, 1), date(2030, 1, 1))
    assert result["updated"] == 1 and list(result["failed"]) == ["000001.SZ"] and result["rows"] == 20
    retry = Vendor()
    BaoStockIndicatorBackfill(repo, retry).backfill(date(2020, 1, 1), date(2030, 1, 1))
    assert [request[0] for request in retry.requests] == ["000001.SZ"]


def test_a_source_that_keeps_failing_stops_the_run_but_keeps_what_was_saved(tmp_path, monkeypatch):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    symbols = [f"{number:06d}.SZ" for number in range(1, 16)]
    CODES.update({symbol: f"sz.{symbol[:6]}" for symbol in symbols})
    repository.save_table("daily_bars", pd.concat([bars(symbol, DAYS[:5]) for symbol in symbols], ignore_index=True))
    monkeypatch.setattr("quant_platform.data.indicator_backfill.CONSECUTIVE_FAILURE_LIMIT", 3)
    vendor = Vendor(failing=set(symbols[2:]))
    with pytest.raises(DataUnavailableError, match="连续 3 只股票取不到.*稍后重新运行即可继续"):
        BaoStockIndicatorBackfill(repository, vendor).backfill(date(2020, 1, 1), date(2030, 1, 1))
    assert len(vendor.requests) == 5 and sorted(repository.daily_indicator_spans().index) == symbols[:2]


def test_the_background_job_accepts_indicators_alone_and_runs_only_that(tmp_path, monkeypatch):
    calls = []
    service = SimpleNamespace(
        app={"app": {"runtime_dir": str(tmp_path)}},
        run_closed_loop=lambda *args, **options: calls.append("closed_loop") or {},
        backfill_daily_indicators=lambda start, end, progress=None: calls.append(("indicators", start, end)) or {"failed": {}, "rows": 3},
    )
    monkeypatch.setattr("quant_platform.application.data_service.DataCenterService", lambda config: service)
    folder = tmp_path / "job"
    folder.mkdir()
    job = {"config": "configs/app.yaml", "start_date": "2024-01-02", "end_date": "2024-06-28", "datasets": ["indicators"]}
    assert data_jobs.attempt(folder, job) == 0
    assert calls == [("indicators", date(2024, 1, 2), date(2024, 6, 28))]
    assert data_jobs.read_json(folder / "result.json") == {"daily_indicators": {"failed": {}, "rows": 3}}

    calls.clear()
    service.backfill_daily_indicators = lambda start, end, progress=None: calls.append("indicators") or {"failed": {"000001.SZ": "x"}}
    assert data_jobs.attempt(folder, {**job, "datasets": ["bars", "indicators"]}) == 2      # 有失败的股票：任务标记为部分完成
    assert calls == ["closed_loop", "indicators"]
    with pytest.raises(ValueError, match="有效的数据集"):
        data_jobs.DataJobs(tmp_path / "jobs").start(date(2024, 1, 2), date(2024, 6, 28), ["valuation"])


# --------------------------------------------------------------------------- #
# Factors
# --------------------------------------------------------------------------- #


def factor(name):
    return default_registry().get(name)


def wide(frame):
    return frame.pivot(index="date", columns="symbol", values="value")


def test_value_factors_are_the_inverse_of_the_stored_ratios(repo):
    stored = normalize_baostock_indicators(vendor_rows("000001.SZ", DAYS))
    stored.loc[3, "pe_ttm"] = -20.0                                   # 亏损：盈利收益率为负
    repo.save_table(INDICATOR_TABLE, stored)
    loaded = repo.get_daily_bars(["000001.SZ"], extras=INDICATOR_COLUMNS)
    ep = wide(factor("ep_ttm").compute(loaded))["000001.SZ"]
    assert ep.iloc[0] == pytest.approx(1 / 10.0) and ep.iloc[3] == pytest.approx(-1 / 20.0)
    assert wide(factor("bp_mrq").compute(loaded))["000001.SZ"].iloc[0] == pytest.approx(0.8)
    assert wide(factor("sp_ttm").compute(loaded))["000001.SZ"].iloc[0] == pytest.approx(0.4)
    assert wide(factor("cfp_ttm").compute(loaded))["000001.SZ"].iloc[0] == pytest.approx(-0.125)
    assert {factor(name).direction for name in ("ep_ttm", "bp_mrq", "sp_ttm", "cfp_ttm")} == {1}


def test_turnover_factors_use_rolling_averages(repo):
    stored = normalize_baostock_indicators(vendor_rows("000001.SZ", DAYS))
    stored["turnover_rate"] = [1.0] * 25 + [3.0] * 5
    repo.save_table(INDICATOR_TABLE, stored)
    loaded = repo.get_daily_bars(["000001.SZ"], extras=["turnover_rate"])
    average = wide(factor("turnover_20").compute(loaded))["000001.SZ"]
    assert average.index[0] == DAYS[19] and average.iloc[0] == pytest.approx(1.0) and average.iloc[-1] == pytest.approx(1.5)
    change = wide(factor("turnover_change_20").compute(loaded))["000001.SZ"]
    assert change.iloc[0] == pytest.approx(0.0) and change.iloc[-1] == pytest.approx(3.0 / 1.5 - 1)
    assert factor("turnover_20").direction == -1


def test_using_an_indicator_factor_before_downloading_indicators_says_what_to_do(repo):
    with pytest.raises(ValueError, match="因子 ep_ttm 缺少字段"):
        factor("ep_ttm").compute(repo.get_daily_bars(["000001.SZ"]))
    with pytest.raises(ValueError) as error:
        FactorEvaluator(repo).evaluate(factor("ep_ttm"), DAYS[0].date(), DAYS[-1].date(), horizon=1, n_groups=2)
    assert str(error.value) == MISSING_INDICATORS_MESSAGE


def test_evaluation_and_strategies_ask_for_the_indicator_columns_they_need(repo):
    for symbol in ("000001.SZ", "600519.SH"):
        days = DAYS if symbol == "000001.SZ" else DAYS[5:25]
        repo.save_table(INDICATOR_TABLE, normalize_baostock_indicators(vendor_rows(symbol, days, pe=8.0 if symbol == "000001.SZ" else 30.0)))
    asked = []
    original = repo.get_daily_bars

    def recording(*args, **options):
        asked.append(tuple(options.get("extras", ())))
        return original(*args, **options)

    repo.get_daily_bars = recording
    report = FactorEvaluator(repo).evaluate(factor("ep_ttm"), DAYS[5].date(), DAYS[20].date(), horizon=1, n_groups=2)
    assert ("pe_ttm",) in asked and report is not None
    asked.clear()
    FactorEvaluator(repo).evaluate(factor("momentum_20"), DAYS[21].date(), DAYS[24].date(), horizon=1, n_groups=2)
    assert all(request == () for request in asked)             # 用不到指标的因子不读那张表

    strategy = FactorCompositeStrategy.from_parameters("s", {"factors_json": '[{"name": "ep_ttm", "weight": 1.0}, {"name": "turnover_20", "weight": 1.0}]'})
    assert indicator_columns(strategy.data_fields) == ["pe_ttm", "turnover_rate"]
