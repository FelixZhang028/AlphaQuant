"""首页新手引导向导（guide）的单元测试。"""

from __future__ import annotations

from quant_platform.web.guide import StepState, build_guide_steps


def test_fresh_install_guides_to_data_update_first() -> None:
    steps = build_guide_steps(
        configured_symbols=0,
        symbols_with_sufficient_history=0,
        has_strategies=False,
        has_backtest_runs=False,
        has_paper_accounts=False,
    )
    assert [step.key for step in steps] == [
        "data",
        "universe",
        "strategy",
        "backtest",
        "review",
        "paper",
    ]
    assert steps[0].state == StepState.CURRENT
    assert all(step.state == StepState.TODO for step in steps[1:])


def test_partial_progress_marks_first_incomplete_as_current() -> None:
    steps = build_guide_steps(
        configured_symbols=8,
        symbols_with_sufficient_history=8,
        has_strategies=True,
        has_backtest_runs=False,
        has_paper_accounts=False,
    )
    assert [step.state for step in steps] == [
        StepState.DONE,
        StepState.DONE,
        StepState.DONE,
        StepState.CURRENT,
        StepState.TODO,
        StepState.TODO,
    ]


def test_insufficient_history_blocks_data_step() -> None:
    steps = build_guide_steps(
        configured_symbols=8,
        symbols_with_sufficient_history=5,
        has_strategies=True,
        has_backtest_runs=True,
        has_paper_accounts=True,
    )
    assert steps[0].state == StepState.CURRENT
    assert steps[0].key == "data"


def test_all_done_when_everything_complete() -> None:
    steps = build_guide_steps(
        configured_symbols=8,
        symbols_with_sufficient_history=8,
        has_strategies=True,
        has_backtest_runs=True,
        has_paper_accounts=True,
    )
    assert all(step.state == StepState.DONE for step in steps)
    assert all(step.page for step in steps)
    assert all(step.action for step in steps)
