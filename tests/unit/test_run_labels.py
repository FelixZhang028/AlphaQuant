from pathlib import Path

from quant_platform.backtest.run_store import RunRecord, RunStatus
from quant_platform.web.run_labels import format_run_label


def test_format_run_label_includes_strategy_dates_local_time_and_short_id() -> None:
    record = RunRecord(
        run_id="124762be-8d77-4575-9152-e450cab1c776",
        status=RunStatus.SUCCESS,
        created_at="2026-08-06T09:05:11+00:00",
        updated_at="2026-08-06T09:05:20+00:00",
        strategy_plugin="wt1",
        strategy_id="wt1_v1",
        start_date="2023-01-03",
        end_date="2024-12-31",
        error=None,
        path=Path("runs/124762be-8d77-4575-9152-e450cab1c776"),
    )

    label = format_run_label(record, {"wt1": "WT1号"})

    assert label == (
        "WT1号（wt1_v1）｜区间 2023-01-03～2024-12-31｜"
        "运行 2026-08-06 17:05｜124762be"
    )


def test_format_run_label_handles_legacy_metadata() -> None:
    record = RunRecord(
        run_id="legacy-run",
        status=RunStatus.SUCCESS,
        created_at="",
        updated_at="",
        strategy_plugin="",
        strategy_id="",
        start_date="",
        end_date="",
        error=None,
        path=Path("runs/legacy-run"),
    )

    assert format_run_label(record, {}) == "旧版本策略｜区间未知｜legacy-r"
