"""指数行情不能悄悄错下去：同一天新下载的覆盖旧的；有不可能涨跌的下载不保存；
已存的不可能的点位（例如同代码的股票）会被删掉并重新下载。

2026-10-09 本地的上证指数、科创50、中证1000、中证500 在 9 月 10 日至 10 月 8 日存成了
平安银行等同代码深市股票的价格；以前同一天不覆盖，这些错误一直改不掉。
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_platform.application.data_service import DataCenterService
from quant_platform.core.exceptions import DataQualityError
from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.benchmark_quality import describe, jumps, outliers
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository

DAYS = pd.bdate_range("2026-08-03", "2026-10-19")


def index_bars(symbol="000001.SH", level=3800.0, wrong=slice(None, 0), source="akshare"):
    close = pd.Series([level + i for i in range(len(DAYS))], dtype=float)
    close.iloc[wrong] = 11.7                         # 同代码的股票（平安银行）的价格
    frame = pd.DataFrame({"symbol": symbol, "trade_date": DAYS, "raw_close": close.values, "source": source})
    frame["pre_close"] = frame["raw_close"].shift(1)
    for column in ("raw_open", "raw_high", "raw_low"):
        frame[column] = frame["raw_close"]
    frame["quality_status"] = "OK"
    return frame


def test_impossible_levels_and_moves_are_found():
    bad = index_bars(wrong=slice(27, 42))            # 15 个交易日
    found = outliers(bad)
    assert len(found) == 15 and set(found["raw_close"]) == {11.7}
    assert describe(found) == f"000001.SH {DAYS[27].date()} 至 {DAYS[41].date()}（15 天）"
    assert len(jumps(bad)) == 2                      # 进去和出来的两天
    assert outliers(index_bars()).empty and jumps(index_bars()).empty


def test_the_same_day_is_overwritten_and_the_first_previous_close_comes_from_storage(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("benchmark_bars", index_bars(wrong=slice(27, 42), source="baostock"))

    class Client:
        def index_zh_a_hist(self, symbol, period, start_date, end_date):
            days = DAYS[20:50]
            return pd.DataFrame({"日期": days, "开盘": 3820.0, "最高": 3830.0, "最低": 3810.0,
                                 "收盘": [3800.0 + i for i in range(20, 50)], "成交量": 1.0, "成交额": 1.0})

    ingestor = AkShareCatalogIngestor(RawDataRepository(tmp_path / "raw"), repository, client=Client())
    ingestor.update_benchmark("000001.SH", DAYS[20].date(), DAYS[49].date())
    stored = repository.read_table("benchmark_bars").set_index("trade_date")
    assert len(stored) == len(DAYS)                                     # 覆盖，不重复
    assert outliers(stored.reset_index()).empty and stored.loc[DAYS[30], "raw_close"] == 3830.0
    assert stored.loc[DAYS[20], "pre_close"] == 3819.0                  # 第一天的昨收用已存的前一天补上

    class Wrong(Client):
        def index_zh_a_hist(self, **kwargs):
            frame = super().index_zh_a_hist(**kwargs)
            frame.loc[5:, "收盘"] = 11.7
            return frame

    before = repository.read_table("benchmark_bars")
    with pytest.raises(DataQualityError, match="不可能的涨跌"):
        AkShareCatalogIngestor(RawDataRepository(tmp_path / "raw"), repository, client=Wrong()).update_benchmark(
            "000001.SH", DAYS[20].date(), DAYS[49].date())
    pd.testing.assert_frame_equal(repository.read_table("benchmark_bars"), before)   # 整批不存


def test_repair_removes_wrong_bars_and_downloads_those_weeks_again(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("benchmark_bars", pd.concat([index_bars(wrong=slice(27, 42), source="baostock"),
                                                       index_bars("000300.SH", level=4100.0)]))
    asked = []

    def update_benchmark(start, end, symbol):
        asked.append((symbol, start, end))
        repository.save_table("benchmark_bars", index_bars(symbol).iloc[17:52])

    service = SimpleNamespace(repository=repository, update_benchmark=update_benchmark)
    result = DataCenterService.repair_benchmarks(service)
    assert result["removed"] == 15 and result["errors"] == [] and "000001.SH" in result["detail"]
    assert asked == [("000001.SH", DAYS[27].date() - timedelta(days=10), DAYS[41].date() + timedelta(days=10))]
    stored = repository.read_table("benchmark_bars")
    assert outliers(stored).empty and len(stored) == 2 * len(DAYS)
    assert DataCenterService.repair_benchmarks(service) == {"removed": 0, "detail": "", "errors": []}


def test_replace_table_removes_rows_but_not_from_partitioned_tables(tmp_path):
    repository = ParquetMarketDataRepository(tmp_path / "market")
    repository.save_table("benchmark_bars", index_bars())
    repository.replace_table("benchmark_bars", index_bars().iloc[:10])
    assert len(repository.read_table("benchmark_bars")) == 10
    with pytest.raises(ValueError, match="分区"):
        repository.replace_table("daily_bars", pd.DataFrame({"symbol": ["600000.SH"]}))
