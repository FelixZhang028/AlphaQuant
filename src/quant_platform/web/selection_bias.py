"""Shared selection-bias presentation for audit and optimization pages."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from quant_platform.application.optimization_service import OBJECTIVES
from quant_platform.backtest.credibility import CredibilityReport, audit_persisted_run
from quant_platform.backtest.multiple_testing import (
    SCOPE_NOTE,
    SelectionBiasResult,
    annotate_search,
    load_search,
)


@st.cache_data(ttl=30, max_entries=32, show_spinner=False)
def cached_credibility(run_dir: str, run_kind: str) -> CredibilityReport:
    return audit_persisted_run(run_dir, run_kind=run_kind)


@st.cache_data(ttl=30, max_entries=32, show_spinner=False)
def cached_search(
    directory: str,
    runs_root: str,
) -> tuple[pd.DataFrame, tuple[SelectionBiasResult, ...]]:
    frame, results = load_search(Path(directory), Path(runs_root))
    return annotate_search(frame, results), results


def render_selection_bias(result: SelectionBiasResult) -> None:
    st.subheader("参数搜索偏差")
    feedback = {
        "pass": st.success,
        "warn": st.warning,
        "unavailable": st.warning,
        "not_applicable": st.info,
    }
    feedback[result.status](result.message)
    with st.container(horizontal=True):
        st.metric("本批尝试", str(result.trial_count) if result.trial_count is not None else "未知")
        st.metric("可计算试验", str(result.valid_trials))
        st.metric(
            "估计独立试验",
            str(result.effective_trials) if result.effective_trials is not None else "—",
        )
        st.metric(
            "DSR 显著性",
            f"{result.dsr:.1%}" if result.dsr is not None else "—",
            help="多次试验校正后的显著性概率；95% 为审计参考门槛。",
        )
    st.caption(SCOPE_NOTE)
    with st.expander("计算依据与试验清单"):
        details = [
            {"计算依据": "所属实验", "取值": result.optimization_id or "未关联"},
            {"计算依据": "原排序指标", "取值": OBJECTIVES.get(result.objective or "", "未知")},
            {"计算依据": "年化 Sharpe", "取值": _number(result.observed_sharpe)},
            {"计算依据": "未校正显著性（PSR）", "取值": _number(result.psr, percent=True)},
            {"计算依据": "选择校正门槛（年化 Sharpe）", "取值": _number(result.benchmark_sharpe)},
            {"计算依据": "试验平均相关性", "取值": _number(result.average_correlation)},
            {"计算依据": "最佳与中位 Sharpe 差距（年化）", "取值": _number(result.best_median_gap)},
            {"计算依据": "收益观测数", "取值": str(result.observations or "—")},
        ]
        st.dataframe(pd.DataFrame(details), hide_index=True, width="stretch")
        st.caption(
            "按同一收益日期、频率和无风险利率比较，使用日频 Sharpe、样本偏度与"
            "Pearson 峰度计算；包含未满足回撤约束的有效试验。"
            "DSR 仅衡量 Sharpe 的统计证据。"
            "低于 95%、明显一阶自相关或无法评估均记一条审计警告，不适用不扣分。"
        )
        if result.evidence:
            st.dataframe(pd.DataFrame(result.evidence), hide_index=True, width="stretch")


def _number(value: float | None, *, percent: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:.1%}" if percent else f"{value:.3f}"
