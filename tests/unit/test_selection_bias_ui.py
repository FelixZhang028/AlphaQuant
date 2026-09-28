"""Displayed probabilities, unknown states, six audit dimensions, and optimization table."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.backtest.credibility import audit_credibility
from quant_platform.backtest.metrics import calculate_metrics
from quant_platform.backtest.multiple_testing import SelectionBiasResult
from quant_platform.backtest.run_store import RunRecord, RunStatus
from quant_platform.strategies.spec import ParameterKind, StrategyMetadata, StrategyParameter

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "status,probability",
    [
        ("pass", 0.99),
        ("warn", 0.62),
        ("unavailable", None),
        ("not_applicable", None),
    ],
)
def test_selection_panel_displays_real_probabilities_or_dash(status, probability) -> None:
    def script():
        import streamlit as st

        from quant_platform.web.selection_bias import render_selection_bias

        render_selection_bias(st.session_state["result"])

    app = AppTest.from_function(script)
    app.session_state["result"] = SelectionBiasResult(
        status,
        "试验证据说明。",
        trial_count=100,
        valid_trials=100,
        effective_trials=18,
        dsr=probability,
    )
    app.run()
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["DSR 显著性"] == (f"{probability:.1%}" if probability is not None else "—")
    assert metrics["本批尝试"] == "100"
    assert metrics["估计独立试验"] == "18"
    assert bool(app.warning) == (status in {"warn", "unavailable"})


def _record(path: Path, run_id: str) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        status=RunStatus.SUCCESS,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
        strategy_plugin="fake",
        strategy_id="fake",
        start_date="2023-01-01",
        end_date="2024-01-01",
        error=None,
        path=path,
        run_kind="optimization",
        parent_experiment_id="search-ui",
    )


def test_audit_page_shows_six_dimensions_and_search_warning(tmp_path, monkeypatch) -> None:
    import quant_platform.application.backtest_service as service_module
    import quant_platform.web.selection_bias as ui_module

    record = _record(tmp_path, "audit-ui")
    service = SimpleNamespace(
        available_strategies=lambda: [],
        run_store=SimpleNamespace(list_records=lambda: [record], load_config=lambda _: {}),
    )
    monkeypatch.setattr(service_module, "BacktestService", lambda _: service)
    report = audit_credibility(
        {"status": "VALID", "metrics_reliable": True},
        {},
        {},
        pd.DataFrame(),
        pd.DataFrame(),
        selection_bias=SelectionBiasResult("warn", "多次选参后显著性不足。", dsr=0.62),
    )
    monkeypatch.setattr(ui_module, "cached_credibility", lambda *_: report)
    app = AppTest.from_file(ROOT / "src/quant_platform/web/app_pages/audit_report.py").run()
    assert not app.exception
    metrics = {item.label: item.value for item in app.metric}
    assert metrics["审计维度通过"] == "5/6"
    assert metrics["可信度评级"] == "B"
    assert metrics["DSR 显著性"] == "62.0%"
    dimensions = app.dataframe[0].value
    assert len(dimensions) == 6
    assert dimensions.iloc[-1]["审计维度"] == "参数搜索偏差"
    assert dimensions.iloc[-1]["结论"] == "警告"


def test_optimization_page_renders_dsr_and_preserves_original_rank(tmp_path, monkeypatch) -> None:
    import quant_platform.web.service_cache as cache_module

    runs_root = tmp_path / "runs"
    directory = tmp_path / "optimizations" / "search-ui"
    directory.mkdir(parents=True)
    rows = []
    records = []
    for index in range(2):
        run_id = f"ui-{index}"
        run_dir = runs_root / run_id
        run_dir.mkdir(parents=True)
        values = np.random.default_rng(index).normal(0.001, 0.01, 300)
        nav = pd.DataFrame(
            {
                "trade_date": pd.bdate_range("2023-01-02", periods=301),
                "equity": 100_000 * np.r_[1, np.cumprod(1 + values)],
            }
        )
        nav.to_parquet(run_dir / "nav.parquet")
        rows.append(
            {
                "run_id": run_id,
                "status": "SUCCESS",
                "metrics_reliable": True,
                "rank": index + 1,
                "eligible": True,
                **calculate_metrics(nav),
            }
        )
        records.append(_record(run_dir, run_id))
    pd.DataFrame(rows).to_csv(directory / "results.csv", index=False)
    (directory / "request.json").write_text(
        json.dumps({"combination_count": 2, "objective": "annual_return"}),
        encoding="utf-8",
    )
    request = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="fake",
        strategy_parameters={"lookback": 1},
        start_date=date(2023, 1, 1),
        end_date=date(2024, 1, 1),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )
    metadata = StrategyMetadata(
        "fake",
        "测试策略",
        "测试",
        parameters=(StrategyParameter("lookback", "回看天数", ParameterKind.INTEGER, 1),),
        required_fields=frozenset(),
    )
    service = SimpleNamespace(
        available_strategies=lambda: [metadata],
        runs_root=runs_root,
        request_from_run=lambda _: request,
        run_store=SimpleNamespace(
            list_records=lambda **_: records,
            load_summary=lambda _: rows[0],
        ),
    )
    monkeypatch.setattr(cache_module, "get_backtest_service", lambda _: service)
    app = AppTest.from_file(ROOT / "src/quant_platform/web/app_pages/2_research.py")
    app.session_state["latest_optimization_ui-0"] = str(directory / "results.csv")
    app.run()
    assert not app.exception
    table = next(item.value for item in app.dataframe if "DSR 显著性" in item.value.columns)
    assert table["DSR 显著性"].notna().all()
    assert table["排名"].tolist() == [1, 2]
    assert "参数搜索审计" in table.columns
    # Selecting a different child must display that child's audit, not the first row's.
    app.selectbox(key="optimization_child_ui-0").set_value("ui-1").run()
    assert not app.exception
    assert any("所选组合 DSR 显著性" in item.value for item in app.caption)
