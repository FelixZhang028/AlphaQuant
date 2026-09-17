"""分红送配管道：标准化、摄取与幂等合并。"""

from __future__ import annotations

import pandas as pd
import pytest

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.akshare_catalog import AkShareCatalogIngestor
from quant_platform.data.catalog_normalizers import normalize_akshare_corporate_actions
from quant_platform.data.repositories.parquet_repository import (
    ParquetMarketDataRepository,
)
from quant_platform.data.repositories.raw_repository import RawDataRepository


def _raw_row(
    *,
    cash_per_ten: float | None,
    ex_date: str | None = "2024-07-11",
    status: str = "实施分配",
    bonus_per_ten: float | None = None,
    conversion_per_ten: float | None = None,
) -> dict:
    row = {
        "报告期": "2023-12-31",
        "现金分红-现金分红比例": cash_per_ten,
        "送转股份-送股比例": bonus_per_ten,
        "送转股份-转股比例": conversion_per_ten,
        "除权除息日": ex_date,
        "方案进度": status,
    }
    return row


class TestNormalizeCorporateActions:
    def test_per_ten_units_converted_to_per_share(self) -> None:
        # 真实数据口径：招商银行 2023 年度每 10 股派 19.72 元。
        frame = pd.DataFrame([_raw_row(cash_per_ten=19.72)])
        result = normalize_akshare_corporate_actions(frame, "600036.SH")
        assert len(result) == 1
        row = result.iloc[0]
        assert row["symbol"] == "600036.SH"
        assert row["ex_date"] == pd.Timestamp("2024-07-11")
        assert row["cash_per_share"] == pytest.approx(1.972)
        assert row["share_multiplier"] == pytest.approx(1.0)

    def test_bonus_shares_converted_to_multiplier(self) -> None:
        frame = pd.DataFrame([_raw_row(cash_per_ten=0.0, bonus_per_ten=2.0, conversion_per_ten=3.0)])
        result = normalize_akshare_corporate_actions(frame, "000001.SZ")
        assert result.iloc[0]["cash_per_share"] == pytest.approx(0.0)
        assert result.iloc[0]["share_multiplier"] == pytest.approx(1.5)

    def test_unimplemented_and_dateless_rows_dropped(self) -> None:
        frame = pd.DataFrame(
            [
                _raw_row(cash_per_ten=19.72, status="预披露"),
                _raw_row(cash_per_ten=10.0, ex_date=None),
                _raw_row(cash_per_ten=19.72),
            ]
        )
        result = normalize_akshare_corporate_actions(frame, "600036.SH")
        assert len(result) == 1
        assert result.iloc[0]["cash_per_share"] == pytest.approx(1.972)

    def test_same_day_distributions_merged(self) -> None:
        # 年度分红与特别分红同日除权：现金相加，送转比例相乘。
        frame = pd.DataFrame(
            [
                _raw_row(cash_per_ten=10.0, bonus_per_ten=2.0),
                _raw_row(cash_per_ten=5.0, conversion_per_ten=1.0),
            ]
        )
        result = normalize_akshare_corporate_actions(frame, "000001.SZ")
        assert len(result) == 1
        assert result.iloc[0]["cash_per_share"] == pytest.approx(1.5)
        assert result.iloc[0]["share_multiplier"] == pytest.approx(1.2 * 1.1)

    def test_noop_rows_dropped(self) -> None:
        frame = pd.DataFrame([_raw_row(cash_per_ten=None, ex_date="2024-07-11")])
        result = normalize_akshare_corporate_actions(frame, "600036.SH")
        assert result.empty

    def test_empty_frame_returns_empty_schema(self) -> None:
        result = normalize_akshare_corporate_actions(pd.DataFrame(), "600036.SH")
        assert result.empty
        assert list(result.columns) == [
            "symbol",
            "ex_date",
            "cash_per_share",
            "share_multiplier",
        ]


class _FakeClient:
    def __init__(self, responses: dict[str, pd.DataFrame | Exception]) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def stock_fhps_detail_em(self, symbol: str) -> pd.DataFrame:
        self.calls.append(symbol)
        outcome = self._responses[symbol]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class TestCorporateActionsIngestor:
    def _ingestor(self, tmp_path, responses) -> tuple[AkShareCatalogIngestor, _FakeClient, ParquetMarketDataRepository]:
        client = _FakeClient(responses)
        raw_repo = RawDataRepository(tmp_path / "raw")
        market_repo = ParquetMarketDataRepository(tmp_path / "market")
        return AkShareCatalogIngestor(raw_repo, market_repo, client=client), client, market_repo

    def test_saves_normalized_table_and_raw_snapshot(self, tmp_path) -> None:
        responses = {
            "600036": pd.DataFrame([_raw_row(cash_per_ten=19.72)]),
            "000001": pd.DataFrame([_raw_row(cash_per_ten=7.6, ex_date="2025-07-25")]),
        }
        ingestor, client, market_repo = self._ingestor(tmp_path, responses)

        frame, failures = ingestor.update_corporate_actions(["600036.SH", "000001.SZ"])

        assert failures == []
        assert client.calls == ["600036", "000001"]
        assert len(frame) == 2
        table = market_repo.read_table("corporate_actions")
        assert len(table) == 2
        assert set(table["symbol"]) == {"600036.SH", "000001.SZ"}
        raw_root = tmp_path / "raw" / "akshare" / "corporate_actions_detail"
        assert len(list(raw_root.rglob("metadata.json"))) == 2  # 每只股票一份原始快照

    def test_partial_failure_keeps_other_symbols(self, tmp_path) -> None:
        responses = {
            "600036": pd.DataFrame([_raw_row(cash_per_ten=19.72)]),
            "000001": RuntimeError("eastmoney timeout"),
        }
        ingestor, _, market_repo = self._ingestor(tmp_path, responses)

        frame, failures = ingestor.update_corporate_actions(["600036.SH", "000001.SZ"])

        assert failures == ["000001.SZ"]
        assert len(frame) == 1
        assert market_repo.read_table("corporate_actions")["symbol"].tolist() == ["600036.SH"]

    def test_all_failures_raise(self, tmp_path) -> None:
        responses = {"600036": RuntimeError("proxy error")}
        ingestor, _, _ = self._ingestor(tmp_path, responses)

        with pytest.raises(DataUnavailableError):
            ingestor.update_corporate_actions(["600036.SH"])

    def test_repeated_updates_are_idempotent(self, tmp_path) -> None:
        responses = {"600036": pd.DataFrame([_raw_row(cash_per_ten=19.72)])}
        ingestor, _, market_repo = self._ingestor(tmp_path, responses)

        ingestor.update_corporate_actions(["600036.SH"])
        ingestor.update_corporate_actions(["600036.SH", "600036.SH"])

        table = market_repo.read_table("corporate_actions")
        assert len(table) == 1
        assert table.iloc[0]["cash_per_share"] == pytest.approx(1.972)
