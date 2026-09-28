"""Statistical properties and persisted-search evidence, with deterministic data."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.optimization_service import OptimizationRequest, OptimizationService
from quant_platform.backtest.credibility import audit_persisted_run
from quant_platform.backtest.metrics import calculate_metrics
from quant_platform.backtest.multiple_testing import (
    analyze_search,
    annotate_search,
    deflated_sharpe_ratio,
    load_search,
    load_selection_bias,
)


def _nav(values: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "trade_date": pd.bdate_range("2023-01-02", periods=len(values) + 1),
            "equity": 100_000 * np.r_[1, np.cumprod(1 + values)],
        }
    )


def _search(tmp_path: Path, values: np.ndarray | None = None):
    if values is None:
        values = np.random.default_rng(17).normal(0.0003, 0.01, size=(300, 3))
    runs = tmp_path / "runs"
    directory = tmp_path / "optimizations" / "search-1"
    directory.mkdir(parents=True)
    rows = []
    for index in range(values.shape[1]):
        run_id = f"run-{index}"
        run_dir = runs / run_id
        run_dir.mkdir(parents=True)
        nav = _nav(values[:, index])
        nav.to_parquet(run_dir / "nav.parquet", index=False)
        summary = calculate_metrics(nav)
        (run_dir / "run.json").write_text(
            json.dumps(
                {
                    "run_kind": "optimization",
                    "parent_experiment_id": "search-1",
                }
            ),
            encoding="utf-8",
        )
        rows.append(
            {
                "run_id": run_id,
                "status": "SUCCESS",
                "metrics_reliable": True,
                "eligible": index != 1,
                **summary,
            }
        )
    frame = pd.DataFrame(rows)
    frame.to_csv(directory / "results.csv", index=False)
    (directory / "request.json").write_text(
        json.dumps(
            {
                "combination_count": len(rows),
                "objective": "sharpe",
            }
        ),
        encoding="utf-8",
    )
    return runs, directory, frame


def _analyze(frame: pd.DataFrame, runs: Path, count: int | None = None):
    return analyze_search(
        frame,
        runs,
        optimization_id="search-1",
        objective="sharpe",
        expected_trials=len(frame) if count is None else count,
    )


def test_published_normal_return_example() -> None:
    # Bailey & Lopez de Prado (2014), section "A numerical example", N=88.
    result = deflated_sharpe_ratio(
        sharpe=2.5 / math.sqrt(250),
        sharpe_variance=0.5 / 250,
        trials=88,
        observations=1250,
        skewness=0,
        kurtosis=3,
    )
    assert result.dsr == pytest.approx(0.9505, abs=0.00005)
    assert result.dsr < result.psr


def test_single_trial_has_no_selection_penalty_and_more_trials_reduce_dsr() -> None:
    results = [
        deflated_sharpe_ratio(
            sharpe=0.1,
            sharpe_variance=0.002,
            trials=count,
            observations=500,
            skewness=-1,
            kurtosis=5,
        )
        for count in (1, 2, 10, 100)
    ]
    assert results[0].benchmark == 0
    assert results[0].dsr == results[0].psr
    assert all(a.dsr > b.dsr for a, b in zip(results, results[1:], strict=False))


@pytest.mark.parametrize(
    "overrides",
    [
        {"sharpe": float("nan")},
        {"sharpe_variance": -1},
        {"trials": 0},
        {"observations": 3},
        {"kurtosis": 0},
    ],
)
def test_invalid_formula_inputs_are_rejected(overrides) -> None:
    inputs = dict(
        sharpe=0.1, sharpe_variance=0.002, trials=10, observations=500, skewness=0, kurtosis=3
    )
    with pytest.raises(ValueError):
        deflated_sharpe_ratio(**{**inputs, **overrides})


def test_full_family_includes_ineligible_trials_and_preserves_ranking(tmp_path: Path) -> None:
    runs, directory, original = _search(tmp_path)
    frame, results = load_search(directory, runs)
    assert all(result.valid_trials == 3 for result in results)
    assert all(result.dsr is not None and result.dsr <= result.psr for result in results)
    assert all(1 <= result.effective_trials <= 3 for result in results)
    assert all(item["可计算"] for item in results[0].evidence)
    assert results[0].observed_sharpe == pytest.approx(original.iloc[0]["sharpe"])
    augmented = annotate_search(frame, results)
    pd.testing.assert_frame_equal(augmented[original.columns], frame)


def test_duplicate_return_paths_count_as_one_effective_trial(tmp_path: Path) -> None:
    values = np.random.default_rng(8).normal(0.0004, 0.01, 300)
    runs, _, frame = _search(tmp_path, np.column_stack([values] * 3))
    results = _analyze(frame, runs)
    assert results[0].effective_trials == 1
    assert results[0].dsr == results[0].psr


@pytest.mark.parametrize("problem", ["missing", "failed", "unreliable", "bad_sharpe", "zero"])
def test_incomplete_family_never_reports_a_probability(tmp_path: Path, problem: str) -> None:
    runs, _, frame = _search(tmp_path)
    if problem == "missing":
        (runs / "run-1" / "nav.parquet").unlink()
    elif problem == "failed":
        frame.loc[1, "status"] = "FAILED"
    elif problem == "unreliable":
        frame.loc[1, "metrics_reliable"] = False
    elif problem == "bad_sharpe":
        frame.loc[1, "sharpe"] = 999
    else:
        _nav(np.zeros(300)).to_parquet(runs / "run-1" / "nav.parquet")
    results = _analyze(frame, runs)
    assert results[0].trial_count == 3 and results[0].valid_trials == 2
    assert all(result.status == "unavailable" and result.dsr is None for result in results)


def test_mismatched_dates_and_short_samples_are_unavailable(tmp_path: Path) -> None:
    runs, _, frame = _search(tmp_path)
    path = runs / "run-1" / "nav.parquet"
    nav = pd.read_parquet(path)
    nav["trade_date"] += pd.Timedelta(days=1)
    nav.to_parquet(path)
    assert "日期" in _analyze(frame, runs)[0].message
    nav.iloc[:10].to_parquet(path)
    assert _analyze(frame, runs)[0].valid_trials == 2


def test_trial_count_and_duplicate_ids_are_validated(tmp_path: Path) -> None:
    runs, _, frame = _search(tmp_path)
    assert _analyze(frame, runs, count=4)[0].status == "unavailable"
    frame.loc[1, "run_id"] = "run-0"
    assert _analyze(frame, runs)[0].status == "unavailable"


def test_verified_one_trial_is_not_applicable(tmp_path: Path) -> None:
    runs, _, frame = _search(tmp_path)
    result = _analyze(frame.iloc[:1], runs)[0]
    assert result.status == "not_applicable"
    assert result.dsr is None


def test_audit_links_parent_experiment_and_handles_missing_or_unsafe_parent(tmp_path: Path) -> None:
    runs, directory, _ = _search(tmp_path)
    report = audit_persisted_run(runs / "run-0")
    assert report.selection_bias.optimization_id == "search-1"
    assert report.selection_bias.dsr is not None
    (directory / "request.json").write_text("broken", encoding="utf-8")
    assert audit_persisted_run(runs / "run-0").selection_bias.status == "unavailable"
    for parent in ("../search-1", "missing"):
        result = load_selection_bias(
            runs / "run-0", run_kind="optimization", parent_experiment_id=parent
        )
        assert result.status == "unavailable" and result.dsr is None


def test_optimizer_persists_probabilities_without_changing_original_ranking(tmp_path: Path) -> None:
    class Backtests:
        runs_root = tmp_path / "runs"

        def run(self, request):
            value = request.strategy_parameters["lookback"]
            run_id = f"run-{value}"
            path = self.runs_root / run_id
            path.mkdir(parents=True)
            values = np.random.default_rng(value).normal(0.001 * value, 0.01, 300)
            nav = _nav(values)
            nav.to_parquet(path / "nav.parquet")
            return SimpleNamespace(
                result=SimpleNamespace(
                    run_id=run_id,
                    summary={**calculate_metrics(nav), "metrics_reliable": True},
                )
            )

    request = BacktestRequest(
        strategy_plugin="fake",
        strategy_id="fake",
        strategy_parameters={"lookback": 1},
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
        initial_cash=100_000,
        top_n=5,
        rebalance="weekly",
    )
    result = OptimizationService(Backtests()).run(
        OptimizationRequest(
            base_request=request,
            parameter_grid={"lookback": (1, 2, 3)},
        )
    )
    persisted = pd.read_csv(result.output_dir / "results.csv")
    assert persisted["dsr"].notna().all()
    assert persisted["sharpe"].is_monotonic_decreasing
    _, reloaded = load_search(result.output_dir, Backtests.runs_root)
    assert persisted["dsr"].tolist() == pytest.approx([item.dsr for item in reloaded])
