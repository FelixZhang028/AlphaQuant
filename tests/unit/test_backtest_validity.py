from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.backtest.validity import ValidityStatus, assess_backtest_validity


def test_large_calendar_gap_makes_metrics_invalid() -> None:
    nav = pd.DataFrame(
        {
            "trade_date": ["2023-12-29", "2025-07-28"],
            "equity": [1_000_000.0, 1_370_000.0],
        }
    )

    report = assess_backtest_validity(
        nav,
        start_date=date(2023, 12, 29),
        end_date=date(2025, 7, 28),
        fixed_universe=False,
        evaluation_mode="out_of_sample",
    )

    assert report.status == ValidityStatus.INVALID
    assert not report.metrics_reliable
    assert report.maximum_calendar_gap_days == 577
    assert "EXCESSIVE_DATE_GAP" in {issue.code for issue in report.issues}


def test_complete_in_sample_fixed_universe_is_usable_with_warnings() -> None:
    dates = pd.bdate_range("2024-01-02", "2024-02-29")
    nav = pd.DataFrame({"trade_date": dates, "equity": range(1_000_000, 1_000_000 + len(dates))})
    calendar = pd.DataFrame({"cal_date": dates})

    report = assess_backtest_validity(
        nav,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 2, 29),
        calendar=calendar,
    )

    assert report.status == ValidityStatus.WARNING
    assert report.metrics_reliable
    assert {issue.code for issue in report.issues} == {"FIXED_UNIVERSE", "IN_SAMPLE_ONLY"}
