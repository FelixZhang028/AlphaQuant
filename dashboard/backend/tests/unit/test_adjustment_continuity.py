"""Window-at-a-time updates must keep each stock's adjustment factors on one basis."""
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_platform.application.data_service import CONTINUITY_LOOKBACK_DAYS, DataCenterService
from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.application import data_service
from quant_platform.data.adjustment import (
    AdjustmentSourceChanged,
    ContinuousAdjustmentRepository,
    align_adjustment_basis,
)
from quant_platform.data.baostock_backfill import BaoStockRangeBackfill
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository

SYMBOL = "000001.SZ"
# Raw closes around a cash dividend of 0.25 that goes ex on 2026-09-24.
CLOSES = {"2026-09-22": 11.71, "2026-09-23": 11.60, "2026-09-24": 11.30, "2026-09-30": 11.57,
          "2026-10-08": 11.78, "2026-10-09": 11.59}
EX_DATE = "2026-09-24"
STEP = 11.35 / 11.60  # the price ratio the dividend removes


def bars(rows, symbol=SYMBOL, source="baostock:qfq/raw", provider="baostock"):
    return pd.DataFrame([{"symbol": symbol, "trade_date": pd.Timestamp(day), "raw_close": 10.0, "adj_factor": factor,
                          "adjusted_close": None if factor is None else 10.0 * factor, "adjustment_source": source,
                          "source": provider}
                         for day, factor in rows])


def factors(frame):
    return {day.date().isoformat(): round(value, 6) for day, value in zip(frame["trade_date"], frame["adj_factor"], strict=True)}


def test_new_rows_are_rescaled_to_the_history_before_the_window():
    stored = bars([("2026-09-23", 1.0)])
    # The provider's new basis is 1.0 on the last day, so earlier days come back smaller.
    incoming = bars([("2026-09-23", STEP), ("2026-09-24", 1.0), ("2026-10-08", 1.0)])
    aligned, unaligned, source_changed = align_adjustment_basis(incoming, stored, {SYMBOL})
    assert unaligned == [] and source_changed == {}
    assert factors(aligned) == {"2026-09-23": 1.0, "2026-09-24": round(1 / STEP, 6), "2026-10-08": round(1 / STEP, 6)}
    assert aligned["adjusted_close"].round(6).tolist() == [10.0, round(10 / STEP, 6), round(10 / STEP, 6)]
    assert set(aligned["adjustment_source"]) == {"baostock:qfq/raw;continuity_anchor=2026-09-23"}


def test_the_earliest_shared_day_anchors_even_when_later_stored_rows_are_broken():
    # 10-08 was saved on the wrong basis earlier; replaying the window from 09-23 must repair it.
    stored = bars([("2026-09-23", 1.0), ("2026-09-24", 1 / STEP), ("2026-10-08", 1.0)])
    incoming = bars([("2026-09-23", STEP), ("2026-09-24", 1.0), ("2026-10-08", 1.0)])
    aligned, *_ = align_adjustment_basis(incoming, stored, {SYMBOL})
    assert factors(aligned)["2026-10-08"] == round(1 / STEP, 6)


def test_rows_without_a_shared_day_are_withheld_instead_of_saved_on_a_guess():
    incoming = pd.concat([bars([("2026-10-08", 1.0)]), bars([("2026-10-08", 1.0)], symbol="600519.SH"),
                          bars([("2026-10-08", 1.0)], symbol="300750.SZ")], ignore_index=True)
    stored = bars([("2026-10-08", 2.0)], symbol="600519.SH")
    aligned, unaligned, _ = align_adjustment_basis(incoming, stored, {SYMBOL, "600519.SH"})
    assert unaligned == [SYMBOL]
    assert sorted(aligned["symbol"]) == ["300750.SZ", "600519.SH"]
    by_symbol = aligned.set_index("symbol")
    assert by_symbol.loc["600519.SH", "adj_factor"] == 2.0
    # A first download has nothing to align with and keeps the provider's basis untouched.
    assert by_symbol.loc["300750.SZ", "adj_factor"] == 1.0
    assert by_symbol.loc["300750.SZ", "adjustment_source"] == "baostock:qfq/raw"


def test_rows_that_carry_no_factor_pass_through():
    incoming = bars([("2026-10-08", None)], source="pytdx:unavailable")
    aligned, unaligned, _ = align_adjustment_basis(incoming, bars([]), {SYMBOL})
    assert unaligned == [] and len(aligned) == 1 and aligned["adjustment_source"].iloc[0] == "pytdx:unavailable"
    without_column = incoming.drop(columns=["adj_factor"])
    assert align_adjustment_basis(without_column, bars([]), {SYMBOL})[0] is without_column


def test_last_adjusted_bar_is_found_newest_year_first_and_ignores_rows_without_factors(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", pd.concat([
        bars([("2025-12-30", 1.0), ("2026-09-30", 1.0), ("2026-10-08", None)]),
        bars([("2025-06-30", 1.0)], symbol="600519.SH"),
    ], ignore_index=True))
    found = repo.last_adjusted_bar_dates([SYMBOL, "600519.SH", "300750.SZ"], before=date(2026, 10, 9))
    assert found == {SYMBOL: date(2026, 9, 30), "600519.SH": date(2025, 6, 30)}
    assert repo.last_adjusted_bar_dates([SYMBOL], before=date(2026, 9, 30)) == {SYMBOL: date(2025, 12, 30)}
    assert repo.last_adjusted_bar_dates([SYMBOL, "600519.SH"], before=date(2026, 10, 9), since=date(2026, 9, 1)) == {
        SYMBOL: date(2026, 9, 30)}
    legacy = ParquetMarketDataRepository(tmp_path / "no-factors")
    legacy.save_table("daily_bars", bars([("2026-09-30", 1.0)]).drop(columns=["adj_factor"]))
    assert legacy.last_adjusted_bar_dates([SYMBOL], before=date(2026, 10, 9)) == {}


def test_update_start_reaches_back_to_the_last_stored_bar_within_a_bound(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", pd.concat([
        bars([("2026-09-30", 1.0)]),
        bars([("2020-01-02", 1.0)], symbol="600519.SH"),  # stale for years: must not drag the request back
    ], ignore_index=True))
    service = SimpleNamespace(repository=repo)
    start = DataCenterService._continuity_start(service, [SYMBOL, "600519.SH", "300750.SZ"], date(2026, 10, 8))
    assert start == date(2026, 9, 30)
    assert CONTINUITY_LOOKBACK_DAYS >= 30  # long enough to span the longest market holidays
    assert DataCenterService._continuity_start(service, ["300750.SZ"], date(2026, 10, 8)) == date(2026, 10, 8)


class DividendProvider:
    """Mimics BaoStock: forward-adjusted closes are relative to the last day of each request."""

    def get_security_metadata(self, symbols):
        return pd.DataFrame({"symbol": symbols, "code_name": "平安银行", "ipoDate": "1991-04-03", "outDate": "", "status": "1"})

    def get_history_range(self, symbol, start_date, end_date, *, adjustflag):
        days = [day for day in CLOSES if start_date.isoformat() <= day <= end_date.isoformat()]
        if not days:
            return pd.DataFrame()

        def basis(day):  # cumulative factor on a fixed, request-independent basis
            return STEP if day < EX_DATE else 1.0

        rows = []
        for day in days:
            close = CLOSES[day] * (basis(day) / basis(days[-1]) if adjustflag == "2" else 1.0)
            rows.append({"date": day, "code": "sz.000001", "open": close, "high": close, "low": close, "close": close,
                         "preclose": close, "volume": 1000, "amount": 10000.0, "adjustflag": adjustflag,
                         "tradestatus": "1", "pctChg": 0.0, "isST": "0"})
        return pd.DataFrame(rows)

    def close(self):
        pass


def test_each_fetched_symbol_is_reported_as_it_completes(tmp_path):
    # 每日更新靠它判断任务没有卡住：每下载完一只股票报一次。
    seen = []
    view = ContinuousAdjustmentRepository(ParquetMarketDataRepository(tmp_path / "market"))
    BaoStockRangeBackfill(RawDataRepository(tmp_path / "raw"), view, DividendProvider()).backfill(
        [SYMBOL], date(2026, 9, 22), date(2026, 9, 23), on_symbol=seen.append)
    assert seen == [SYMBOL]


def test_incremental_baostock_updates_stay_continuous_across_a_dividend(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    raw = RawDataRepository(tmp_path / "raw")

    def update(start, end):
        view = ContinuousAdjustmentRepository(repo)
        BaoStockRangeBackfill(raw, view, DividendProvider()).backfill([SYMBOL], start, end)
        return view.unaligned

    update(date(2026, 9, 22), date(2026, 9, 23))            # before the dividend: factor 1.0
    assert update(date(2026, 9, 23), date(2026, 9, 30)) == []  # window ends after the ex-date
    with pytest.raises(DataUnavailableError, match="2026-09-30"):
        update(date(2026, 10, 8), date(2026, 10, 9))        # after the holiday, no shared day: refused
    assert update(date(2026, 9, 30), date(2026, 10, 9)) == []  # the service's extended start

    stored = repo.get_daily_bars([SYMBOL])
    by_day = factors(stored)
    assert by_day["2026-09-22"] == by_day["2026-09-23"] == 1.0
    step_up = round(1 / STEP, 6)
    assert by_day["2026-09-24"] == by_day["2026-09-30"] == by_day["2026-10-08"] == by_day["2026-10-09"] == step_up
    # Exactly one factor change, on the ex-date; the adjusted series has no jump at any update seam.
    changes = stored.loc[stored["adj_factor"].round(9).diff().fillna(0).ne(0), "trade_date"].dt.date.tolist()
    assert changes == [date(2026, 9, 24)]
    assert stored["adjusted_close"].round(4).tolist() == [round(CLOSES[day] * by_day[day], 4) for day in CLOSES]


def test_other_tables_and_factorless_bars_are_saved_unchanged(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    view = ContinuousAdjustmentRepository(repo)
    view.save_table("trade_calendar", pd.DataFrame({"cal_date": [pd.Timestamp("2026-10-08")], "is_open": 1}))
    view.save_table("daily_bars", bars([("2026-10-08", 1.0)]).drop(columns=["adj_factor"]))
    assert len(view.read_table("trade_calendar")) == 1 and len(view.get_daily_bars([SYMBOL])) == 1


def test_another_providers_rows_never_continue_a_stored_history():
    stored = bars([("2026-09-23", 1.0)])
    # AkShare subtracts the dividend instead of scaling, so its ratio drifts day by day.
    incoming = pd.concat([
        bars([("2026-09-23", 0.978448), ("2026-09-24", 1.0)], provider="akshare"),
        bars([("2026-09-24", 1.0)], symbol="300750.SZ", provider="akshare"),
    ], ignore_index=True)
    aligned, unaligned, source_changed = align_adjustment_basis(incoming, stored, {SYMBOL})
    assert source_changed == {SYMBOL: ("baostock", "akshare")} and unaligned == []
    # A stock with nothing stored may still be downloaded from the other provider.
    assert aligned["symbol"].tolist() == ["300750.SZ"]
    same = align_adjustment_basis(bars([("2026-09-23", 0.5), ("2026-09-24", 0.6)]), stored, {SYMBOL})
    assert same.source_changed == {} and len(same.bars) == 2


def test_the_repository_view_refuses_a_save_made_only_of_another_providers_rows(tmp_path):
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", bars([("2026-09-22", 1.0), ("2026-09-23", 1.0)]))
    view = ContinuousAdjustmentRepository(repo)
    with pytest.raises(AdjustmentSourceChanged, match="历史行情来自 baostock，不能用 akshare 的数据续接"):
        view.save_table("daily_bars", bars([("2026-09-23", 0.978448), ("2026-09-24", 1.0)], provider="akshare"))
    assert view.source_changed == {SYMBOL: ("baostock", "akshare")}
    stored = repo.get_daily_bars([SYMBOL])
    assert stored["source"].eq("baostock").all() and len(stored) == 2


class Unreachable:
    def __init__(self, *args, **kwargs):
        pass

    def backfill(self, symbols, start_date, end_date):
        raise DataUnavailableError("BaoStock login failed")


class Fallback:
    """Stands in for the AkShare backfill: saves its own rows through the repository it is given."""

    def __init__(self, raw_repository, market_repository, **kwargs):
        self.repository = market_repository

    def backfill(self, symbols, start_date, end_date):
        self.repository.save_table("daily_bars", pd.concat(
            [bars([("2026-09-23", 0.978448), ("2026-09-24", 1.0)], symbol=symbol, provider="akshare") for symbol in symbols],
            ignore_index=True))
        return "report"


def service_with(repo, order):
    names = {"baostock": "BaoStock", "akshare": "AkShare"}
    return SimpleNamespace(
        repository=repo, raw_repository=None, _akshare_client=lambda: None,
        sources=SimpleNamespace(resolve_market_sources=lambda requested: order, fallback_enabled=lambda allowed: True,
                                baostock_provider=lambda: None, source_display_name=names.get))


def test_when_the_usual_provider_is_down_the_fallback_cannot_overwrite_its_history(tmp_path, monkeypatch):
    monkeypatch.setattr(data_service, "BaoStockRangeBackfill", Unreachable)
    monkeypatch.setattr(data_service, "AkShareRangeBackfill", Fallback)
    repo = ParquetMarketDataRepository(tmp_path / "market")
    repo.save_table("daily_bars", bars([("2026-09-22", 1.0), ("2026-09-23", 1.0)]))
    run = DataCenterService._run_market_backfill
    window = (date(2026, 9, 23), date(2026, 9, 24))

    with pytest.raises(DataUnavailableError, match="BaoStock 暂时连不上.*历史行情来自 BaoStock，不能用 AkShare 的数据续接.*请稍后重试"):
        run(service_with(repo, ["baostock", "akshare"]), [SYMBOL], *window)
    assert repo.get_daily_bars([SYMBOL])["source"].eq("baostock").all()

    # Asking for the other provider directly is refused for what it is, not as an outage.
    with pytest.raises(AdjustmentSourceChanged) as refused:
        run(service_with(repo, ["akshare"]), [SYMBOL], *window)
    assert "暂时连不上" not in str(refused.value) and "不能用 AkShare 的数据续接" in str(refused.value)

    # Stocks with nothing stored still get the fallback; the others are reported, not written.
    source, _, attempts, withheld = run(service_with(repo, ["baostock", "akshare"]), [SYMBOL, "300750.SZ"], *window)
    assert source == "akshare" and [item["status"] for item in attempts] == ["failed", "success"]
    assert withheld.source_changed == {SYMBOL: ("baostock", "akshare")} and withheld.unaligned == []
    assert repo.get_daily_bars(["300750.SZ"])["source"].eq("akshare").all()
    assert len(repo.get_daily_bars([SYMBOL])) == 2
