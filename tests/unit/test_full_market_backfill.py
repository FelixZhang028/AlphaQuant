"""全市场数据闭环（含退市股、历史成分、退市结算）的单元测试。"""

import time
from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.full_market_backfill import (
    FullMarketBackfill,
    _ProgressWatchdog,
)
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository

RANGE_START = date(2024, 1, 2)
RANGE_END = date(2024, 12, 31)


class FakeFullMarketProvider:
    """模拟 BaoStock：全量列表（含指数与退市股）+ 每只两根日线。"""

    def __init__(self, fail_symbols: set[str] | None = None) -> None:
        self.login_count = 0
        self.close_count = 0
        self.range_calls: list[tuple[str, str]] = []
        self.fail_symbols = fail_symbols or set()

    def login(self) -> None:
        self.login_count += 1

    def close(self) -> None:
        self.close_count += 1

    def get_security_master(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "code": ["sz.000001", "sh.600001", "sh.000300", "sz.300001"],
                "code_name": ["平安银行", "退市钢铁", "沪深300指数", "次新股"],
                "ipoDate": ["1991-04-03", "1998-01-22", "2005-01-01", "2024-06-03"],
                "outDate": ["", "2024-03-29", "", ""],
                "type": ["1", "1", "2", "1"],
                "status": ["1", "0", "1", "1"],
            }
        )

    def get_history_range(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        *,
        adjustflag: str,
    ) -> pd.DataFrame:
        if symbol in self.fail_symbols:
            raise RuntimeError(f"boom: {symbol}")
        self.range_calls.append((symbol, adjustflag))
        if symbol == "600001.SH":
            dates = ["2024-01-02", "2024-03-28"]
        elif symbol == "300001.SZ":
            dates = ["2024-06-04", "2024-06-05"]
        else:
            dates = ["2024-01-02", "2024-01-03"]
        close = ["9.50", "9.60"] if adjustflag == "2" else ["10.00", "10.10"]
        return pd.DataFrame(
            {
                "date": dates,
                "code": [symbol.split(".")[1].lower() + "." + symbol.split(".")[0]] * 2,
                "open": ["9.90", "10.00"],
                "high": ["10.10", "10.20"],
                "low": ["9.80", "9.90"],
                "close": close,
                "preclose": ["9.80", "10.00"],
                "volume": ["100000", "120000"],
                "amount": ["1000000", "1200000"],
                "adjustflag": [adjustflag, adjustflag],
                "tradestatus": ["1", "1"],
                "pctChg": ["2", "1"],
                "isST": ["0", "0"],
            }
        )


class FakeAkShareClient:
    """模拟 AkShare：当前在市列表 + 空分红明细。"""

    def stock_info_a_code_name(self) -> pd.DataFrame:
        return pd.DataFrame({"code": ["000001"], "name": ["平安银行"]})

    def stock_fhps_detail_em(self, symbol: str) -> pd.DataFrame:
        return pd.DataFrame(
            columns=["除权除息日", "方案进度", "现金分红-现金分红比例"]
        )


def _backfill(tmp_path: Path, provider=None) -> FullMarketBackfill:
    return FullMarketBackfill(
        RawDataRepository(tmp_path / "raw"),
        ParquetMarketDataRepository(tmp_path / "market"),
        provider or FakeFullMarketProvider(),
        akshare_client=FakeAkShareClient(),
        state_path=tmp_path / "state.json",
    )


def test_refresh_security_master_keeps_delisted_and_filters_non_stocks(
    tmp_path: Path,
) -> None:
    backfill = _backfill(tmp_path)

    master = backfill.refresh_security_master()

    assert set(master["symbol"]) == {"000001.SZ", "600001.SH", "300001.SZ"}
    delisted = master[master["symbol"].eq("600001.SH")].iloc[0]
    assert delisted["list_status"] == "D"
    assert pd.Timestamp(delisted["delist_date"]) == pd.Timestamp("2024-03-29")
    listed = master[master["symbol"].eq("000001.SZ")].iloc[0]
    assert listed["list_status"] == "L"
    assert pd.isna(listed["delist_date"])
    stored = backfill.market_repository.read_table("security_master")
    assert set(stored["symbol"]) == set(master["symbol"])


def test_backfill_daily_bars_batches_and_resumes(tmp_path: Path) -> None:
    provider = FakeFullMarketProvider()
    backfill = _backfill(tmp_path, provider)

    stats = backfill.backfill_daily_bars(
        RANGE_START, RANGE_END, batch_size=2, resume=True
    )

    # 3 只股票（指数被过滤），全部完成且无失败
    assert stats["total"] == 3
    assert stats["done"] == 3
    assert stats["failed"] == {}
    bars = backfill.market_repository.read_table("daily_bars")
    assert set(bars["symbol"]) == {"000001.SZ", "600001.SH", "300001.SZ"}
    status_by_symbol = bars.groupby("symbol")["quality_status"].agg(set)
    assert set(status_by_symbol["000001.SZ"]) == {"OK"}
    assert set(status_by_symbol["600001.SH"]) == {"OK"}
    # 次新上市 10 日窗口内涨跌停不可验证，UNKNOWN_STATUS 属预期设计
    assert set(status_by_symbol["300001.SZ"]) == {"UNKNOWN_STATUS"}
    first_calls = len(provider.range_calls)

    # 断点续传：同一区间重跑不再发起新请求
    resumed = backfill.backfill_daily_bars(
        RANGE_START, RANGE_END, batch_size=2, resume=True
    )
    assert resumed["done"] == 3
    assert len(provider.range_calls) == first_calls
    assert (tmp_path / "state.json").exists()

    # 区间变化后断点自动作废，重新抓取
    backfill.backfill_daily_bars(RANGE_START, RANGE_END, batch_size=2, resume=False)
    assert len(provider.range_calls) == first_calls * 2


def test_backfill_daily_bars_tolerates_single_failures(tmp_path: Path) -> None:
    provider = FakeFullMarketProvider(fail_symbols={"300001.SZ"})
    backfill = _backfill(tmp_path, provider)

    stats = backfill.backfill_daily_bars(
        RANGE_START, RANGE_END, batch_size=1, resume=True
    )

    assert stats["done"] == 2
    assert set(stats["failed"]) == {"300001.SZ"}
    bars = backfill.market_repository.read_table("daily_bars")
    assert "300001.SZ" not in set(bars["symbol"])
    # 失败证券记录在断点中，重跑时跳过
    resumed = backfill.backfill_daily_bars(
        RANGE_START, RANGE_END, batch_size=1, resume=True
    )
    assert resumed["done"] == 2


def _write_membership_fixture(market: ParquetMarketDataRepository) -> None:
    market.save_table(
        "security_master",
        pd.DataFrame(
            {
                "symbol": [
                    "000001.SZ",
                    "600001.SH",
                    "600099.SH",
                    "600100.SH",
                ],
                "name": ["在市", "退市", "长期停牌", "无行情"],
                "exchange": ["SZ", "SH", "SH", "SH"],
                "list_date": pd.to_datetime(
                    ["2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01"]
                ),
                "delist_date": pd.to_datetime(
                    [pd.NaT, "2024-03-29", pd.NaT, pd.NaT]
                ),
                "list_status": ["L", "D", "L", "L"],
                "source": ["baostock"] * 4,
            }
        ),
    )
    market.save_table(
        "daily_bars",
        pd.DataFrame(
            {
                "symbol": ["000001.SZ"] * 2 + ["600001.SH"] * 2 + ["600099.SH"],
                "trade_date": pd.to_datetime(
                    [
                        "2024-01-02",
                        "2024-06-28",
                        "2024-01-02",
                        "2024-03-28",
                        "2022-01-04",
                    ]
                ),
            }
        ),
    )


def test_build_universe_membership_applies_listing_rules(tmp_path: Path) -> None:
    backfill = _backfill(tmp_path)
    _write_membership_fixture(backfill.market_repository)

    membership = backfill.build_universe_membership()

    rows = membership.set_index("symbol")
    # 无行情证券不入池
    assert "600100.SH" not in rows.index
    # 在市：effective_from = max(上市日, 首根行情)，effective_to 留空
    active = rows.loc["000001.SZ"]
    assert pd.Timestamp(active["effective_from"]) == pd.Timestamp("2024-01-02")
    assert pd.isna(active["effective_to"])
    assert pd.Timestamp(active["known_at"]) == pd.Timestamp("2024-01-02")
    # 退市：effective_to = min(退市日, 最后行情日)
    delisted = rows.loc["600001.SH"]
    assert pd.Timestamp(delisted["effective_to"]) == pd.Timestamp("2024-03-28")
    # 长期停牌（数据截断）：成分止于最后行情日
    stale = rows.loc["600099.SH"]
    assert pd.Timestamp(stale["effective_to"]) == pd.Timestamp("2022-01-04")
    stored = backfill.market_repository.read_table("universe_membership")
    assert len(stored) == 3


def test_build_universe_membership_replaces_stale_rows(tmp_path: Path) -> None:
    backfill = _backfill(tmp_path)
    market = backfill.market_repository
    market.save_table(
        "universe_membership",
        pd.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "effective_from": pd.to_datetime(["2023-01-01"]),
                "effective_to": pd.to_datetime([pd.NaT]),
                "known_at": pd.to_datetime(["2023-01-01"]),
                "source": ["rule:listing_period"],
            }
        ),
    )
    _write_membership_fixture(market)

    membership = backfill.build_universe_membership()

    rows = membership[membership["symbol"].eq("000001.SZ")]
    # 旧的 2023 区间被替换，不残留双区间
    assert len(rows) == 1
    assert pd.Timestamp(rows.iloc[0]["effective_from"]) == pd.Timestamp("2024-01-02")


def test_build_delisting_settlements_uses_last_close_before_delist(
    tmp_path: Path,
) -> None:
    backfill = _backfill(tmp_path)
    market = backfill.market_repository
    market.save_table(
        "security_master",
        pd.DataFrame(
            {
                "symbol": ["600001.SH"],
                "name": ["退市钢铁"],
                "exchange": ["SH"],
                "list_date": pd.to_datetime(["2020-01-01"]),
                "delist_date": pd.to_datetime(["2024-03-29"]),
                "list_status": ["D"],
                "source": ["baostock"],
            }
        ),
    )
    market.save_table(
        "daily_bars",
        pd.DataFrame(
            {
                "symbol": ["600001.SH"] * 3,
                "trade_date": pd.to_datetime(
                    ["2024-03-27", "2024-03-28", "2024-04-15"]
                ),
                "raw_close": [3.10, 3.30, 9.99],
            }
        ),
    )

    settlements = backfill.build_delisting_settlements()

    assert len(settlements) == 1
    row = settlements.iloc[0]
    assert pd.Timestamp(row["settlement_date"]) == pd.Timestamp("2024-03-28")
    assert float(row["cash_per_share"]) == 3.30


def test_progress_watchdog_tracks_heartbeat_and_pause() -> None:
    watchdog = _ProgressWatchdog(timeout_seconds=0.05)

    # 未启动时不监控
    assert not watchdog.expired()
    watchdog._arm()
    assert not watchdog.expired()
    time.sleep(0.1)
    # 超时无心跳 → 判定过期
    assert watchdog.expired()
    # 喂狗重置
    watchdog.feed()
    assert not watchdog.expired()
    # 暂停窗口内不判过期
    watchdog.pause()
    time.sleep(0.1)
    assert not watchdog.expired()
    # 恢复监控并顺带喂狗
    watchdog.resume()
    assert not watchdog.expired()
    time.sleep(0.1)
    assert watchdog.expired()


def test_run_closed_loop_with_watchdog_completes(tmp_path: Path) -> None:
    provider = FakeFullMarketProvider()
    backfill = _backfill(tmp_path, provider)

    results = backfill.run_closed_loop(
        RANGE_START, RANGE_END, batch_size=2, watchdog_timeout=600.0
    )

    assert results["daily_bars"]["done"] == 3
    assert results["corporate_actions"]["done"] == 3


def test_run_closed_loop_writes_all_datasets_and_manifests(tmp_path: Path) -> None:
    provider = FakeFullMarketProvider()
    backfill = _backfill(tmp_path, provider)

    results = backfill.run_closed_loop(RANGE_START, RANGE_END, batch_size=2)

    market = backfill.market_repository
    assert results["security_master"]["delisted"] == 1
    assert results["daily_bars"]["done"] == 3
    assert results["corporate_actions"]["done"] == 3
    assert results["universe_membership"]["symbols"] == 3
    assert results["delisting_settlements"]["rows"] == 1
    for dataset in (
        "security_master",
        "daily_bars",
        "corporate_actions",
        "universe_membership",
        "delisting_settlements",
    ):
        manifests = market.read_table("data_manifests")
        succeeded = manifests[
            manifests["dataset"].eq(dataset) & manifests["status"].eq("SUCCESS")
        ]
        assert not succeeded.empty, dataset


def test_akshare_master_refresh_preserves_closed_loop_rows(tmp_path: Path) -> None:
    market = ParquetMarketDataRepository(tmp_path / "market")
    market.save_table(
        "security_master",
        pd.DataFrame(
            {
                "symbol": ["000001.SZ", "600001.SH"],
                "name": ["平安银行", "退市钢铁"],
                "exchange": ["SZ", "SH"],
                "list_date": pd.to_datetime(["1991-04-03", "1998-01-22"]),
                "delist_date": pd.to_datetime([pd.NaT, "2024-03-29"]),
                "list_status": ["L", "D"],
                "source": ["baostock"] * 2,
            }
        ),
    )
    catalog = AkShareCatalogIngestor(
        RawDataRepository(tmp_path / "raw"), market, client=FakeAkShareClient()
    )

    catalog.update_security_master()

    master = market.read_table("security_master").set_index("symbol")
    # 在市股票保留闭环 PIT 字段，不被 AkShare 空日期覆盖
    assert pd.Timestamp(master.loc["000001.SZ", "list_date"]) == pd.Timestamp(
        "1991-04-03"
    )
    assert master.loc["000001.SZ", "source"] == "baostock"
    # 退市股完整保留
    assert master.loc["600001.SH", "list_status"] == "D"
