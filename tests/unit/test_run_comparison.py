from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from quant_platform.backtest.run_store import RunRecord, RunStatus
from quant_platform.web.run_comparison import (
    comparison_display_frame,
    run_catalog_frame,
)


def test_run_catalog_and_comparison_are_localized_for_shared_pages() -> None:
    record = RunRecord(
        run_id="run-1",
        status=RunStatus.SUCCESS,
        created_at="2026-08-07T00:00:00+00:00",
        updated_at="2026-08-07T00:01:00+00:00",
        strategy_plugin="sch1",
        strategy_id="sch1_opt_001",
        start_date="2024-01-01",
        end_date="2024-12-31",
        error=None,
        path=Path("runs/run-1"),
        run_kind="optimization",
        parent_experiment_id="experiment-1",
        baseline_run_id="baseline-1",
    )
    metadata = SimpleNamespace(
        parameters=(SimpleNamespace(name="lookback", label="观察窗口"),)
    )
    comparison = pd.DataFrame(
        {
            "run_id": ["run-1"],
            "strategy": ["sch1"],
            "parameters": ['{"lookback": 20}'],
            "annual_return": [0.1],
        }
    )

    catalog = run_catalog_frame([record], {"sch1": "SCH1号"})
    display = comparison_display_frame(
        comparison, {"sch1": metadata}, {"sch1": "SCH1号"}
    )

    assert catalog.iloc[0]["run_kind"] == "optimization"
    assert catalog.iloc[0]["baseline_run_id"] == "baseline-1"
    assert display.iloc[0]["strategy"] == "SCH1号"
    assert "观察窗口" in display.iloc[0]["parameters"]
