"""The cached per-symbol bar summary gives the same numbers as counting every stored row."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.routes import workspace
from quant_platform.application.data_service import DataCenterService
from quant_platform.data.coverage import calculate_daily_coverage, coverage_from_summary
from quant_platform.data.repositories import parquet_repository
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository

SESSIONS = pd.bdate_range("2024-12-23", "2025-01-17")
CALENDAR = pd.DataFrame({"cal_date": SESSIONS, "is_open": 1})


def bars(symbol, days, **columns):
    frame = pd.DataFrame({"symbol": symbol, "trade_date": pd.to_datetime(list(days)), "raw_open": 10.0, "raw_close": 10.5,
                          "quality_status": "OK"})
    for name, value in columns.items():
        frame[name] = value
    return frame


def market():
    """Three stocks across two calendar years: one complete, one with gaps and flags, one short."""

    gappy = bars("000002.SZ", SESSIONS[[0, 1, 2, 9, 10, 15]])
    gappy.loc[1, "quality_status"] = "UNKNOWN_STATUS"
    gappy.loc[2, "quality_status"] = None
    gappy.loc[3, "raw_open"] = np.nan
    gappy.loc[4, "raw_close"] = np.nan
    return pd.concat([bars("000001.SZ", SESSIONS), gappy, bars("600519.SH", SESSIONS[12:])], ignore_index=True)


@pytest.fixture
def repo(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("daily_bars", market())
    repository.save_table("trade_calendar", CALENDAR)
    return repository


def same_coverage(summary, stored, calendar, symbols):
    expected, expected_rows = calculate_daily_coverage(stored, calendar, symbols)
    actual, actual_rows = coverage_from_summary(summary, calendar, symbols)
    assert actual == expected
    pd.testing.assert_frame_equal(actual_rows, expected_rows)
    return actual


def test_summary_counts_rows_dates_and_rows_that_need_attention(repo):
    summary = repo.daily_bar_summary()
    assert list(summary.index) == ["000001.SZ", "000002.SZ", "600519.SH"]
    assert summary.loc["000001.SZ"].to_dict() == {
        "rows": 20, "unique_rows": 20, "start": SESSIONS[0], "end": SESSIONS[-1], "unknown_status_rows": 0, "missing_price_rows": 0}
    assert summary.loc["000002.SZ", ["rows", "unique_rows", "unknown_status_rows", "missing_price_rows"]].tolist() == [6, 6, 2, 2]
    assert (summary.loc["600519.SH", "start"], summary.loc["600519.SH", "rows"]) == (SESSIONS[12], 8)


@pytest.mark.parametrize("symbols", [
    None,
    ["000001.SZ", "000002.SZ"],
    ["000002.SZ", "300750.SZ"],          # 一只有行情，一只完全没有
    ["600519.SH"],
])
def test_coverage_from_the_summary_equals_counting_every_row(repo, symbols):
    coverage = same_coverage(repo.daily_bar_summary(), repo.read_table("daily_bars"), CALENDAR, symbols)
    assert coverage.rows > 0


def test_symbols_without_any_bars_give_the_same_empty_result(repo):
    stored = repo.read_table("daily_bars")
    assert coverage_from_summary(repo.daily_bar_summary(), CALENDAR, ["300750.SZ"])[0] == calculate_daily_coverage(stored, CALENDAR, ["300750.SZ"])[0]
    with pytest.raises(ValueError, match="trade calendar"):
        coverage_from_summary(repo.daily_bar_summary(), pd.DataFrame())


def test_duplicate_rows_in_an_unsorted_single_file_are_counted_once(tmp_path):
    # 旧版的单文件布局，可以有重复行和乱序：汇总不能依赖“文件已排序、键唯一”。
    root = tmp_path / "market"
    root.mkdir()
    frame = pd.concat([market(), bars("000001.SZ", SESSIONS[[3, 3, 7]]), bars("000002.SZ", SESSIONS[[9]])], ignore_index=True)
    frame = frame.sample(frac=1, random_state=3).reset_index(drop=True)
    frame.to_parquet(root / "daily_bars.parquet")
    repository = ParquetMarketDataRepository(root)
    summary = repository.daily_bar_summary()
    assert summary.loc["000001.SZ", ["rows", "unique_rows"]].tolist() == [23, 20]
    assert summary.loc["000002.SZ", ["rows", "unique_rows"]].tolist() == [7, 6]
    coverage = same_coverage(summary, repository.read_table("daily_bars"), CALENDAR, None)
    assert coverage.duplicate_rows == 4


def test_the_same_day_stored_in_two_files_is_counted_once(repo):
    # 同一个分区里多出一个文件，和原有文件的日期重叠。
    partition = next((repo.root / "daily_bars").glob("year=2025"))
    bars("000001.SZ", SESSIONS[[10, 11]]).to_parquet(partition / "extra.parquet")
    summary = repo.daily_bar_summary()
    assert summary.loc["000001.SZ", ["rows", "unique_rows"]].tolist() == [22, 20]
    same_coverage(summary, repo.read_table("daily_bars"), CALENDAR, None)


def test_tables_without_status_or_price_columns_keep_the_row_by_row_meaning(tmp_path):
    root = tmp_path / "market"
    root.mkdir()
    market().drop(columns=["quality_status", "raw_open"]).to_parquet(root / "daily_bars.parquet")
    repository = ParquetMarketDataRepository(root)
    coverage = same_coverage(repository.daily_bar_summary(), repository.read_table("daily_bars"), CALENDAR, None)
    # 没有状态列：都算正常；没有开盘价列：每一行都算缺价格。
    assert (coverage.unknown_status_rows, coverage.missing_price_rows) == (0, 34)


def test_the_summary_is_reused_until_a_bar_file_changes(repo, monkeypatch):
    computed = []
    original = parquet_repository._summarize_daily_bars
    monkeypatch.setattr(parquet_repository, "_summarize_daily_bars", lambda files: computed.append(len(files)) or original(files))

    first = repo.daily_bar_summary()
    first.loc["000001.SZ", "rows"] = -1            # 调用方改自己拿到的那份，不影响缓存
    again = ParquetMarketDataRepository(repo.root).daily_bar_summary()
    assert len(computed) == 1 and again.loc["000001.SZ", "rows"] == 20

    repo.save_table("daily_bars", bars("300750.SZ", SESSIONS[-3:]))
    updated = repo.daily_bar_summary()
    assert len(computed) == 2
    assert updated.loc["300750.SZ", ["rows", "start"]].tolist() == [3, SESSIONS[-3]]
    assert repo.daily_bar_summary().equals(updated) and len(computed) == 2


def test_an_empty_repository_has_an_empty_summary(tmp_path):
    summary = ParquetMarketDataRepository(tmp_path / "market").daily_bar_summary()
    assert summary.empty and list(summary.columns) == ["rows", "unique_rows", "start", "end", "unknown_status_rows", "missing_price_rows"]


def service(repo, symbols):
    return SimpleNamespace(repository=repo, configured_symbols=symbols, benchmark_symbol="000300.SH")


def test_the_overview_reads_no_prices_and_matches_the_row_by_row_overview(repo, monkeypatch):
    symbols = ["000001.SZ", "000002.SZ", "300750.SZ"]
    expected, expected_rows = calculate_daily_coverage(repo.read_table("daily_bars"), CALENDAR, symbols)
    read = []
    original = repo.read_table
    monkeypatch.setattr(repo, "read_table", lambda name: read.append(name) or original(name))
    overview = DataCenterService.overview(service(repo, symbols))
    assert "daily_bars" not in read
    assert overview.market == expected
    pd.testing.assert_frame_equal(overview.per_symbol, expected_rows)


def test_without_a_trade_calendar_the_overview_still_counts_every_row(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("daily_bars", market())
    overview = DataCenterService.overview(service(repository, []))
    expected, _ = calculate_daily_coverage(repository.read_table("daily_bars"), pd.DataFrame(), [])
    assert overview.market == expected and overview.market.rows == 34


def test_universe_statistics_come_from_the_summary(repo, monkeypatch):
    monkeypatch.setattr(workspace, "market_repository", lambda: repo)
    stats = workspace._local_symbol_stats()
    assert stats["000002.SZ"] == {"local_rows": 6, "start_date": "2024-12-23", "end_date": "2025-01-13"}
    assert sorted(stats) == ["000001.SZ", "000002.SZ", "600519.SH"]
