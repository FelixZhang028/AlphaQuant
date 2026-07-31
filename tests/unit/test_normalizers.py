import pandas as pd

from quant_platform.data.normalizers import (
    compose_standard_daily,
    normalize_tushare_daily,
)


def test_tushare_units_and_standard_composition() -> None:
    raw = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "open": 10.0,
                "high": 11.0,
                "low": 9.5,
                "close": 10.5,
                "pre_close": 9.9,
                "vol": 123.0,
                "amount": 456.0,
            }
        ]
    )
    bars = normalize_tushare_daily(raw)
    standard = compose_standard_daily(
        bars,
        pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": "20240102", "adj_factor": 2.0}]),
        pd.DataFrame(
            [
                {
                    "ts_code": "000001.SZ",
                    "trade_date": "20240102",
                    "up_limit": 10.89,
                    "down_limit": 8.91,
                }
            ]
        ),
        pd.DataFrame(),
    )

    assert bars.iloc[0]["volume"] == 12_300
    assert bars.iloc[0]["amount"] == 456_000
    assert standard.iloc[0]["adjusted_close"] == 21.0
    assert standard.iloc[0]["quality_status"] == "OK"
