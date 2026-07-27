import pandas as pd

from quant_platform.data.network import ProxyResilientAkShareClient


class EastmoneyUnavailableClient:
    def stock_zh_a_hist(self, **parameters: object) -> pd.DataFrame:
        raise ConnectionError("remote end closed connection")

    def stock_zh_a_daily(self, **parameters: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": ["2024-01-02"],
                "open": [10.0],
                "high": [10.2],
                "low": [9.8],
                "close": [10.1],
                "volume": [100_000.0],
                "amount": [1_000_000.0],
            }
        )

    def index_zh_a_hist(self, **parameters: object) -> pd.DataFrame:
        raise ConnectionError("remote end closed connection")

    def stock_zh_index_daily(self, **parameters: object) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "date": ["2024-01-01", "2024-01-02", "2024-01-04"],
                "open": [3300.0, 3310.0, 3320.0],
                "high": [3310.0, 3320.0, 3330.0],
                "low": [3290.0, 3300.0, 3310.0],
                "close": [3305.0, 3315.0, 3325.0],
                "volume": [100_000, 110_000, 120_000],
            }
        )


def test_stock_history_uses_sina_when_eastmoney_is_unavailable() -> None:
    client = ProxyResilientAkShareClient(EastmoneyUnavailableClient())

    result = client.stock_zh_a_hist(
        symbol="000001",
        period="daily",
        start_date="20240102",
        end_date="20240102",
        adjust="",
    )

    assert list(result["股票代码"]) == ["000001"]
    assert list(result["收盘"]) == [10.1]
    assert list(result["成交量"]) == [1000.0]


def test_index_history_uses_sina_and_filters_requested_dates() -> None:
    client = ProxyResilientAkShareClient(EastmoneyUnavailableClient())

    result = client.index_zh_a_hist(
        symbol="000300",
        period="daily",
        start_date="20240102",
        end_date="20240103",
    )

    assert list(result["日期"].dt.strftime("%Y-%m-%d")) == ["2024-01-02"]
    assert list(result["收盘"]) == [3315.0]
