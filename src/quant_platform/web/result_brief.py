"""Evidence-based plain-language summaries; never infer validation from returns."""

from math import isfinite

import streamlit as st


def number(summary, key):
    value = summary.get(key)
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if isfinite(value) else None
    except (TypeError, ValueError):
        return None


def result_brief(summary, *, out_of_sample=False, linked_oos=0):
    total = number(summary, "cumulative_return")
    benchmark = number(summary, "benchmark_return")
    drawdown = number(summary, "max_drawdown")
    if total is None or benchmark is None:
        comparison = "缺少有效的策略或基准收益，暂时无法判断是否跑赢基准。"
    else:
        diff = total - benchmark
        verb = "高于" if diff > 0 else "低于" if diff < 0 else "等于"
        comparison = (
            f"策略累计收益 {total:.2%}，基准 {benchmark:.2%}；"
            f"{verb}基准 {abs(diff) * 100:.2f} 个百分点。"
        )
    risk = (
        "缺少最大回撤数据，暂时无法评估历史回撤。"
        if drawdown is None
        else f"历史最大回撤 {abs(drawdown):.2%}：从某个资产高点到随后低点，最多回落这一比例。"
        f"以高点资产1万元举例，相当于回落约 {abs(drawdown) * 10000:,.0f} 元；未来可能更大。"
    )
    stability = (
        "当前展示的是样本外区间结果；单个区间不能证明长期有效。"
        if out_of_sample
        else f"已关联 {linked_oos} 条样本外回测，请查看各区间表现；数量不代表已通过验证。"
        if linked_oos
        else "尚未找到关联的样本外结果。当前历史收益不能说明换个时间段仍然有效。"
    )
    return [
        ("是否跑赢基准", comparison),
        ("历史上承受了多大回撤", risk),
        ("换个时间段是否仍有效", stability),
    ]


def open_validation(run_id):
    """Button callback: update navigation before its widget is rendered again."""
    st.session_state["research_baseline_run_id"] = run_id
    st.session_state["backtest_workspace_mode"] = "参数优化与稳健性验证"


def render_result_brief(service, run_id, summary, validity):
    st.subheader("先看懂这次回测")
    if not validity.get("metrics_reliable", False):
        st.warning("本次结果未通过当前可信度审计，以下数值只能用于排查，不能据此判断策略有效。")
    try:
        backtest = service.run_store.load_config(run_id)["app"]["backtest"]
    except (OSError, ValueError, KeyError):
        backtest = {}
    records = service.run_store.list_records(successful_only=True)
    related = [
        r for r in records if r.baseline_run_id == run_id and r.run_kind == "walk_forward_oos"
    ]
    for title, text in result_brief(
        summary,
        out_of_sample=backtest.get("evaluation_mode") == "out_of_sample",
        linked_oos=len(related),
    ):
        st.markdown(f"**{title}**")
        st.write(text)
    st.caption("跑赢基准也可能亏损；本页不会把正收益、单次高夏普或样本外记录数标记为“策略有效”。")
    st.button(
        "继续做样本外验证",
        key="brief_oos_" + run_id,
        disabled=not validity.get("metrics_reliable", False),
        on_click=open_validation,
        args=(run_id,),
    )
