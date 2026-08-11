from __future__ import annotations

from datetime import date

import pandas as pd

from quant_platform.backtest.validity import (
    ValidityStatus,
    assess_backtest_validity,
    load_persisted_validity,
)


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


def test_unknown_market_status_makes_metrics_unreliable_but_keeps_diagnostics() -> None:
    dates = pd.bdate_range("2024-01-02", "2024-02-29")
    nav = pd.DataFrame({"trade_date": dates, "equity": 1_000_000.0})
    orders = pd.DataFrame(
        {
            "status": ["REJECTED"],
            "reject_reason": ["UNKNOWN_MARKET_STATUS"],
        }
    )

    report = assess_backtest_validity(
        nav,
        start_date=date(2024, 1, 2),
        end_date=date(2024, 2, 29),
        orders=orders,
        unknown_market_rows=42,
        unknown_market_symbols=3,
        fixed_universe=False,
        evaluation_mode="out_of_sample",
    )

    assert report.status == ValidityStatus.INVALID
    assert not report.metrics_reliable
    assert not report.blocks_completion
    assert report.unknown_market_rows == 42
    assert report.unknown_market_symbols == 3
    assert report.unknown_status_orders == 1
    assert {issue.code for issue in report.issues} == {
        "UNKNOWN_MARKET_STATUS",
        "UNKNOWN_STATUS_ORDERS",
    }


def test_old_validity_report_fails_closed_as_legacy_unverified(tmp_path) -> None:
    (tmp_path / "validity_report.json").write_text(
        '{"status":"WARNING","metrics_reliable":true}', encoding="utf-8"
    )

    report = load_persisted_validity(tmp_path)

    assert report["status"] == "INVALID"
    assert report["metrics_reliable"] is False
    assert report["legacy_unverified"] is True
    assert report["issues"][0]["code"] == "LEGACY_UNVERIFIED"
