from datetime import date

import pandas as pd
import pytest

from quant_platform.core.exceptions import DataUnavailableError
from quant_platform.data.normalizers import canonical_symbol, normalize_baostock_daily
from quant_platform.data.providers.baostock_provider import BaoStockDataProvider


class FakeResult:
    def __init__(
        self,
        frame: pd.DataFrame | None = None,
        error_code: str = "0",
        error_msg: str = "",
    ) -> None:
        self.frame = frame if frame is not None else pd.DataFrame()
        self.error_code = error_code
        self.error_msg = error_msg

    def get_data(self) -> pd.DataFrame:
        return self.frame


class FakeBaoStock:
    def __init__(self) -> None:
        self.login_calls = 0
        self.logout_calls = 0
        self.history_calls: list[dict[str, object]] = []

    def login(self) -> FakeResult:
        self.login_calls += 1
        return FakeResult()

    def logout(self) -> FakeResult:
        self.logout_calls += 1
        return FakeResult()

    def query_history_k_data_plus(self, *args: object, **kwargs: object) -> FakeResult:
        self.history_calls.append({"args": args, "kwargs": kwargs})
        return FakeResult(pd.DataFrame({"date": ["2024-01-02"]}))


def test_provider_uses_one_session_and_canonical_symbol_format() -> None:
    client = FakeBaoStock()
    provider = BaoStockDataProvider(client)

    provider.get_history_range(
        "000001.SZ", date(2024, 1, 2), date(2024, 1, 3), adjustflag="3"
    )
    provider.get_history_range(
        "600000.SH", date(2024, 1, 2), date(2024, 1, 3), adjustflag="2"
    )
    provider.close()

    assert client.login_calls == 1
    assert client.logout_calls == 1
    assert client.history_calls[0]["args"][0] == "sz.000001"  # type: ignore[index]
    assert client.history_calls[1]["args"][0] == "sh.600000"  # type: ignore[index]
    assert canonical_symbol("sh.600000") == "600000.SH"


def test_provider_errors_fail_closed() -> None:
    class FailedLogin(FakeBaoStock):
        def login(self) -> FakeResult:
            return FakeResult(error_code="1001", error_msg="offline")

    with pytest.raises(DataUnavailableError, match="offline"):
        BaoStockDataProvider(FailedLogin(), retries=1).login()


def test_provider_retries_a_transient_login_failure(monkeypatch: object) -> None:
    class FlakyLogin(FakeBaoStock):
        def login(self) -> FakeResult:
            self.login_calls += 1
            if self.login_calls == 1:
                return FakeResult(error_code="1001", error_msg="temporary")
            return FakeResult()

    monkeypatch.setattr(  # type: ignore[attr-defined]
        "quant_platform.data.providers.baostock_provider.time.sleep", lambda _: None
    )
    client = FlakyLogin()
    provider = BaoStockDataProvider(client, retries=2)

    provider.login()

    assert client.login_calls == 2


def test_normalizer_preserves_known_and_unknown_status() -> None:
    raw = pd.DataFrame(
        {
            "date": ["2024-01-02", "2024-01-03"],
            "code": ["sz.000001", "sz.000001"],
            "open": ["10", "10.2"],
            "high": ["10.5", "10.6"],
            "low": ["9.8", "10.1"],
            "close": ["10.2", "10.4"],
            "preclose": ["9.9", "10.2"],
            "volume": ["1000", "1200"],
            "amount": ["10000", "12000"],
            "tradestatus": ["1", ""],
            "isST": ["0", "x"],
        }
    )

    result = normalize_baostock_daily(raw)

    assert result.iloc[0]["is_suspended"] == False  # noqa: E712
    assert result.iloc[0]["is_st"] == False  # noqa: E712
    assert bool(result.iloc[0]["status_known"])
    assert pd.isna(result.iloc[1]["is_suspended"])
    assert not bool(result.iloc[1]["status_known"])
