from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_platform.core.exceptions import DataCapabilityNotSupported
from quant_platform.data.normalizers import normalize_pytdx_daily
from quant_platform.data.providers.pytdx_provider import (
    PyTdxDataProvider,
    PyTdxRequestMetrics,
)
from quant_platform.data.pytdx_backfill import PyTdxRangeBackfill
from quant_platform.data.repositories.parquet_repository import ParquetMarketDataRepository
from quant_platform.data.repositories.raw_repository import RawDataRepository


def _raw_bars() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datetime": ["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
            "open": [9.8, 10.0, 10.4, 10.8],
            "high": [10.1, 10.6, 11.0, 11.3],
            "low": [9.7, 9.9, 10.3, 10.7],
            "close": [10.0, 10.5, 10.8, 11.0],
            "vol": [1000, 1100, 1200, 1300],
            "amount": [10_000, 11_550, 12_960, 14_300],
        }
    )


class FakeTdxApi:
    connected_hosts: list[str] = []

    def __init__(self) -> None:
        self.host = ""

    def connect(self, host: str, port: int, time_out: float) -> bool:
        self.host = host
        self.connected_hosts.append(host)
        return host == "good"

    def disconnect(self) -> None:
        return None

    def get_security_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int,
        count: int,
    ) -> list[dict[str, object]]:
        assert category == 9
        assert market == 0
        assert code == "000001"
        raw = _raw_bars().iloc[::-1].reset_index(drop=True)
        return raw.iloc[start : start + count].to_dict("records")


class StaticTdxProvider:
    def __init__(self) -> None:
        self.last_metrics: PyTdxRequestMetrics | None = None

    def get_history_range(
        self, symbol: str, start_date: date, end_date: date
    ) -> pd.DataFrame:
        self.last_metrics = PyTdxRequestMetrics("mock:7709", 2, 4)
        return _raw_bars()


def test_pytdx_provider_rotates_servers_and_pages_backwards() -> None:
    FakeTdxApi.connected_hosts = []
    provider = PyTdxDataProvider(
        servers=["bad:7709", "good:7709"],
        retries=1,
        page_size=2,
        client_factory=FakeTdxApi,
    )

    result = provider.get_history_range(
        "000001.SZ", date(2024, 1, 3), date(2024, 1, 5)
    )

    assert len(result) == 4
    assert provider.last_metrics == PyTdxRequestMetrics("good:7709", 2, 4)
    provider.get_history_range("000001.SZ", date(2024, 1, 3), date(2024, 1, 5))
    assert FakeTdxApi.connected_hosts == ["bad", "good", "good"]
    with pytest.raises(DataCapabilityNotSupported, match="SH/SZ only"):
        provider.get_history_range("830001.BJ", date(2024, 1, 2), date(2024, 1, 5))


def test_normalize_pytdx_daily_converts_lots_and_builds_pre_close() -> None:
    bars = normalize_pytdx_daily(_raw_bars(), "000001.SZ")

    assert list(bars["symbol"].unique()) == ["000001.SZ"]
    assert bars.iloc[1]["pre_close"] == 10.0
    assert bars.iloc[-1]["volume"] == 130_000
    assert bars.iloc[-1]["source"] == "pytdx"


def test_pytdx_backfill_only_inserts_missing_keys(tmp_path: Path) -> None:
    market = ParquetMarketDataRepository(tmp_path / "market")
    existing = normalize_pytdx_daily(_raw_bars().iloc[[1]], "000001.SZ")
    existing["adjusted_close"] = 10.4
    existing["adj_factor"] = 1.0
    existing["up_limit"] = 11.0
    existing["down_limit"] = 9.0
    existing["is_suspended"] = False
    existing["is_st"] = False
    existing["is_listed"] = True
    existing["quality_status"] = "OK"
    existing["source"] = "baostock"
    market.save_table("daily_bars", existing)

    backfill = PyTdxRangeBackfill(
        RawDataRepository(tmp_path / "raw"),
        market,
        StaticTdxProvider(),  # type: ignore[arg-type]
    )
    report = backfill.backfill(
        ["000001.SZ"], date(2024, 1, 3), date(2024, 1, 5)
    )
    bars = market.get_daily_bars(
        ["000001.SZ"], date(2024, 1, 3), date(2024, 1, 5)
    )

    protected = bars[bars["trade_date"].eq(pd.Timestamp("2024-01-03"))].iloc[0]
    assert protected["source"] == "baostock"
    assert protected["quality_status"] == "OK"
    assert set(bars["trade_date"]) == {
        pd.Timestamp("2024-01-03"),
        pd.Timestamp("2024-01-04"),
        pd.Timestamp("2024-01-05"),
    }
    assert report.status_counts == {"MISSING_ADJ_FACTOR": 3}
    assert backfill.metadata["inserted_rows"] == 2
    assert backfill.metadata["skipped_existing_rows"] == 1
