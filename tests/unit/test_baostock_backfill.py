from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.data.baostock_backfill import BaoStockRangeBackfill
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository


class FakeBaoStockProvider:
    def __init__(self) -> None:
        self.closed = False

    def get_security_metadata(self, symbols: list[str]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "code": ["sz.000001"],
                "code_name": ["平安银行"],
                "ipoDate": ["1991-04-03"],
                "outDate": [""],
                "type": ["1"],
                "status": ["1"],
                "symbol": ["000001.SZ"],
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
        close = ["9.50", "10.50"] if adjustflag == "2" else ["10.00", "11.00"]
        return pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "code": ["sz.000001", "sz.000001"],
                "open": ["9.90", "10.20"],
                "high": ["10.10", "11.20"],
                "low": ["9.80", "10.10"],
                "close": close,
                "preclose": ["9.80", "10.00"],
                "volume": ["100000", "120000"],
                "amount": ["1000000", "1200000"],
                "adjustflag": [adjustflag, adjustflag],
                "tradestatus": ["1", "1"],
                "pctChg": ["2", "10"],
                "isST": ["0", "0"],
            }
        )

    def close(self) -> None:
        self.closed = True


def test_baostock_backfill_publishes_verified_status_and_provenance(tmp_path: Path) -> None:
    provider = FakeBaoStockProvider()
    market = ParquetMarketDataRepository(tmp_path / "market")
    backfill = BaoStockRangeBackfill(
        RawDataRepository(tmp_path / "raw"), market, provider=provider
    )

    report = backfill.backfill(["000001.SZ"], date(2024, 1, 2), date(2024, 1, 3))
    bars = market.get_daily_bars()

    assert provider.closed
    assert report.ok_rows == 2
    assert set(bars["quality_status"]) == {"OK"}
    assert list(bars["up_limit"]) == [10.78, 11.0]
    assert list(bars["down_limit"]) == [8.82, 9.0]
    assert set(bars["status_source"]) == {"baostock:tradestatus,isST"}
    assert set(bars["price_limit_source"]) == {"derived"}
    assert set(bars["adjustment_source"]) == {"baostock:qfq/raw"}
    assert list(bars["adjusted_close"]) == [9.5, 10.5]
