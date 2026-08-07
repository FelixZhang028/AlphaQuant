from datetime import date

import pandas as pd
import pytest

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import normalize_ifind_daily
from quant_platform.data.providers.ifind_provider import IFindDataProvider


class FakeIFind:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def THS_iFinDLogin(self, username: str, password: str) -> int:
        self.calls.append(("login", username, password))
        return 0

    def THS_HQ(self, *args: object) -> dict[str, object]:
        self.calls.append(("hq", *args))
        adjusted = "CPS:2" in str(args[2])
        close = [9.5, 10.5] if adjusted else [10.0, 11.0]
        return {
            "errorcode": 0,
            "tables": pd.DataFrame(
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
            ),
        }

    def THS_DateQuery(self, *args: object) -> dict[str, object]:
        self.calls.append(("calendar", *args))
        return {
            "errorcode": 0,
            "data": [{"time": "2024-01-02"}, {"time": "2024-01-03"}],
        }


def test_ifind_provider_logs_in_lazily_and_derives_adjustment_factor() -> None:
    client = FakeIFind()
    provider = IFindDataProvider("user", "secret", client=client)

    factors = provider.get_adjustment_factors(
        date(2024, 1, 2), ["000001.SZ"]
    )
    calendar = provider.get_trade_calendar(date(2024, 1, 2), date(2024, 1, 3))

    assert client.calls[0] == ("login", "user", "secret")
    assert factors.iloc[0]["adj_factor"] == pytest.approx(0.95)
    assert list(calendar["cal_date"]) == [
        pd.Timestamp("2024-01-02"),
        pd.Timestamp("2024-01-03"),
    ]


def test_ifind_normalizer_preserves_share_and_yuan_units() -> None:
    raw = FakeIFind().THS_HQ("", "", "CPS:1", "", "")["tables"]
    assert isinstance(raw, pd.DataFrame)

    result = normalize_ifind_daily(raw)

    assert list(result["symbol"].unique()) == ["000001.SZ"]
    assert list(result["volume"]) == [100_000, 120_000]
    assert list(result["amount"]) == [1_000_000, 1_200_000]
    assert pd.isna(result.iloc[0]["pre_close"])
    assert result.iloc[1]["pre_close"] == 10.0


def test_ifind_parser_flattens_official_nested_table_shape() -> None:
    response = {
        "errorcode": 0,
        "data": {
            "tables": [
                {
                    "thscode": "000001.SZ",
                    "time": ["2024-01-02", "2024-01-03"],
                    "table": {"close": [10.0, 11.0]},
                }
            ]
        },
    }

    result = IFindDataProvider._response_to_frame(response, "THS_HQ")

    assert list(result["thscode"]) == ["000001.SZ", "000001.SZ"]
    assert list(result["time"]) == ["2024-01-02", "2024-01-03"]


class ErrorIFind:
    def THS_HQ(self, *args: object) -> dict[str, object]:
        return {"errorcode": -4302, "errmsg": "permission denied", "tables": []}


def test_ifind_error_is_translated_to_platform_data_error() -> None:
    provider = IFindDataProvider(client=ErrorIFind())

    with pytest.raises(DataUnavailableError, match="permission denied"):
        provider.get_history_range(
            ["000001.SZ"], date(2024, 1, 2), date(2024, 1, 3), cps=1
        )
