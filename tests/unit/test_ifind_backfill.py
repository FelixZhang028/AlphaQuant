from datetime import date
from pathlib import Path

import pandas as pd

from quant_platform.data.ifind_backfill import IFindRangeBackfill
from quant_platform.data.providers.ifind_provider import IFindDataProvider
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository


class FakeHistoryProvider(IFindDataProvider):
    def __init__(self) -> None:
        pass

    def get_history_range(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        *,
        cps: int,
    ) -> pd.DataFrame:
        close = [9.5, 10.5] if cps == 2 else [10.0, 11.0]
        return pd.DataFrame(
            {
                "thscode": ["000001.SZ", "000001.SZ"],
                "time": ["2024-01-02", "2024-01-03"],
                "open": [9.9, 10.2],
                "high": [10.1, 11.2],
                "low": [9.8, 10.1],
                "close": close,
                "volume": [100_000, 120_000],
                "amount": [1_000_000, 1_200_000],
            }
        )


def test_ifind_backfill_publishes_canonical_history(tmp_path: Path) -> None:
    market = ParquetMarketDataRepository(tmp_path / "market")
    backfill = IFindRangeBackfill(
        RawDataRepository(tmp_path / "raw"), market, FakeHistoryProvider()
    )

    report = backfill.backfill(
        ["000001.SZ"], date(2024, 1, 2), date(2024, 1, 3)
    )
    bars = market.get_daily_bars()

    assert report.rows == 2
    assert list(bars["adjusted_close"]) == [9.5, 10.5]
    assert list(bars["source"].unique()) == ["ifind"]
    assert set(bars["quality_status"]) == {"UNKNOWN_STATUS"}
    assert len(list((tmp_path / "raw" / "ifind").rglob("data.parquet"))) == 2
