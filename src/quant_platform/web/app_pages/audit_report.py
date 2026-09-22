"""可信度审计：回测可信度评级、偏差归因与证据链。"""

from __future__ import annotations

import pandas as pd

from quant_platform.web.theme import inject_global_css

inject_global_css()

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.backtest.credibility import audit_persisted_run
from quant_platform.backtest.run_store import RunStatus
from quant_platform.backtest.validity import load_persisted_validity
from quant_platform.web.run_labels import format_run_label

# 评级与证据的视觉语言：A 绿 / B 蓝 / C 黄 / D 红，证据按严重程度着色。
GRADE_FEEDBACK = {"A": st.success, "B": st.info, "C": st.warning, "D": st.error}
STATUS_LABELS = {"pass": "通过", "warn": "警告", "fail": "不通过"}
FINDING_FEEDBACK = {"info": st.caption, "warn": st.warning, "fail": st.error}

st.title("可信度审计")
mode = st.segmented_control(
    "审计对象", ["平台回测", "外部材料"], default="平台回测", key="audit_subject",
    width="stretch",
)
if mode == "外部材料":
    from quant_platform.web.external_audit import render_external_audit

    render_external_audit()
    st.stop()

st.caption(
    "对已完成回测做五维可信度评级：数据完整性、未来函数防护、样本与选股偏差、"
    "成本真实性、容量约束。评级回答的不是'赚不赚钱'，而是'这份结果有多少水分'。"
)

config_path = "configs/app.yaml"  # 正式版固定配置路径，与研究记录页一致
try:
    service = BacktestService(config_path)
except Exception as exc:
    st.error(f"无法加载回测记录：{exc}")
    st.stop()

metadata_by_name = {item.plugin_name: item for item in service.available_strategies()}
strategy_names = {name: item.display_name for name, item in metadata_by_name.items()}
records = [
    record
    for record in service.run_store.list_records()
    if record.status == RunStatus.SUCCESS
]
if not records:
    st.info(
        "暂无可审计的回测记录。请先在「回测与验证」中运行一次回测，"
        "再回到本页查看可信度评级与证据链。",
        icon=":material/fact_check:",
    )
    st.stop()

successful = {record.run_id: record for record in records}
selected_id = st.selectbox(
    "选择回测记录",
    list(successful),
    format_func=lambda run_id: format_run_label(successful[run_id], strategy_names),
    key="audit_report_run",
)
record = successful[selected_id]

try:
    report = audit_persisted_run(record.path, run_kind=record.run_kind)
    validity = load_persisted_validity(record.path)
    config = service.run_store.load_config(record.run_id)
except Exception as exc:
    st.error(f"读取运行记录失败：{exc}")
    st.stop()

# --- 评级仪表盘 -----------------------------------------------------------
passed = sum(dimension.status == "pass" for dimension in report.dimensions)
ratio_text = (
    f"{report.transaction_cost_ratio:.2%}"
    if report.transaction_cost_ratio is not None
    else "—"
)
metric_columns = st.columns(5)
metric_columns[0].metric("可信度评级", report.grade)
metric_columns[1].metric("审计维度通过", f"{passed}/5")
metric_columns[2].metric("绩效指标", "可用" if report.metrics_reliable else "不可用")
metric_columns[3].metric("净值观测", f"{report.observations} 个交易日")
metric_columns[4].metric("成本占初始资金", ratio_text)
GRADE_FEEDBACK[report.grade](f"**可信度评级 {report.grade}**——{report.headline}")

# --- 五维审计总览 ---------------------------------------------------------
st.subheader("五维审计")
dimension_frame = pd.DataFrame(
    [
        {
            "审计维度": dimension.title,
            "结论": STATUS_LABELS[dimension.status],
            "要点": dimension.findings[0].message if dimension.findings else "",
        }
        for dimension in report.dimensions
    ]
)
st.dataframe(dimension_frame, width="stretch", hide_index=True)

st.subheader("维度明细")
for dimension in report.dimensions:
    with st.expander(
        f"{dimension.title}——{STATUS_LABELS[dimension.status]}",
        expanded=dimension.status != "pass",
    ):
        for finding in dimension.findings:
            FINDING_FEEDBACK[finding.severity](finding.message)

# --- 证据链 ---------------------------------------------------------------
st.subheader("证据链")
st.caption("引擎有效性审计的全部原始记录，评级结论均可追溯至此。")
issues = [
    {
        "问题代码": str(issue.get("code", "")),
        "级别": str(issue.get("severity", "")),
        "说明": str(issue.get("message", "")),
    }
    for issue in validity.get("issues", [])
    if isinstance(issue, dict)
]
if issues:
    st.dataframe(pd.DataFrame(issues), width="stretch", hide_index=True)
else:
    st.caption("无有效性问题记录。")

execution = config.get("execution", {})
if isinstance(execution, dict):
    inner = execution.get("execution", {})
    if isinstance(inner, dict):
        execution = inner
historical = execution.get("historical_fees")
participation = execution.get("max_participation")
slippage = execution.get("slippage_rate")
assumptions = pd.DataFrame(
    [
        {
            "审计假设": "历史分期费率",
            "取值": "启用" if historical else ("停用" if historical is False else "未记录"),
        },
        {
            "审计假设": "参与率上限",
            "取值": f"{float(participation):.1%}" if participation is not None else "未记录",
        },
        {
            "审计假设": "滑点率",
            "取值": f"{float(slippage):.3%}" if slippage is not None else "未记录",
        },
        {
            "审计假设": "未知状态策略",
            "取值": str(execution.get("unknown_status_policy", "未记录")),
        },
    ]
)
st.dataframe(assumptions, width="stretch", hide_index=True)
