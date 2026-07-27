import pandas as pd

from quant_platform.data.coverage import calculate_daily_coverage


def test_coverage_reports_missing_symbol_dates_and_unknown_status() -> None:
    calendar = pd.DataFrame(
        {"cal_date": pd.to_datetime(["2024-01-02", "2024-01-03"])}
    )
    bars = pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "trade_date": "2024-01-02",
                "raw_open": 10.0,
                "raw_close": 10.2,
                "quality_status": "UNKNOWN_STATUS",
            }
        ]
    )

    coverage, per_symbol = calculate_daily_coverage(
        bars, calendar, ["000001.SZ"]
    )

    assert coverage.expected_rows == 1
    assert coverage.coverage_ratio == 1.0
    assert coverage.unknown_status_rows == 1
    assert per_symbol.iloc[0]["unknown_status_rows"] == 1
