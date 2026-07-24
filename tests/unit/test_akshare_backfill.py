from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.data.akshare_backfill import AkShareRangeBackfill
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository


class FakeAkShare:
    def stock_zh_a_hist(self, **parameters: object) -> pd.DataFrame:
        adjusted = parameters["adjust"] == "qfq"
        close = [9.5, 10.5] if adjusted else [10.0, 11.0]
        return pd.DataFrame(
            {
                "日期": ["2024-01-02", "2024-01-03"],
                "股票代码": ["000001", "000001"],
                "开盘": [9.9, 10.2],
                "收盘": close,
                "最高": [10.1, 11.2],
                "最低": [9.8, 10.1],
                "成交量": [1000, 1200],
                "成交额": [1_000_000, 1_200_000],
            }
        )


def test_akshare_range_backfill_publishes_degraded_but_usable_data(
    tmp_path: Path,
) -> None:
    market = ParquetMarketDataRepository(tmp_path / "market")
    pipeline = AkShareRangeBackfill(
        RawDataRepository(tmp_path / "raw"), market, client=FakeAkShare()
    )

    report = pipeline.backfill(["000001.SZ"], date(2024, 1, 2), date(2024, 1, 3))
    bars = market.get_daily_bars()

    assert report.rows == 2
    assert set(bars["quality_status"]) == {"UNKNOWN_STATUS"}
    assert list(bars["adjusted_close"]) == [9.5, 10.5]
    assert list(bars["volume"]) == [100_000.0, 120_000.0]
