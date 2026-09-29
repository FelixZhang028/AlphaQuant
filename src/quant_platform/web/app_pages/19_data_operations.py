"""Data preparation and operational tools in one workspace."""

from pathlib import Path

import streamlit as st

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.application.readiness_service import PlatformReadinessService
from quant_platform.web.navigation import render_directory, tool_button


@st.cache_data(ttl=30, max_entries=8, show_spinner=False)
def overview(config_path: str, knowledge_path: str):
    report = PlatformReadinessService(config_path).inspect()
    knowledge_count = len(PriorKnowledgeStore(knowledge_path).list())
    return report.configured_symbols, report.symbols_with_sufficient_history, knowledge_count


st.title("数据与运行")
st.caption("准备研究数据、维护股票范围，查看更新任务与风险记录。")
for column, key, description in zip(
    st.columns(3),
    ("data", "universe", "jobs"),
    (
        "更新行情，为下一次研究准备数据。",
        "维护策略可以选择的股票范围。",
        "检查任务进度和失败原因。",
    ),
    strict=True,
):
    with column.container(border=True):
        tool_button(key, primary=key == "data")
        st.caption(description)

with st.expander("工作区概览", on_change="rerun") as summary:
    if summary.open:
        try:
            configured, history, knowledge = overview(
                str(Path("configs/app.yaml").resolve()),
                str(Path("runtime/prior_knowledge.json").resolve()),
            )
            for column, label, value in zip(
                st.columns(3),
                ("股票池", "历史数据充足", "先验知识"),
                (configured, history, knowledge),
                strict=True,
            ):
                column.metric(label, value)
        except Exception:
            st.info("暂时无法读取概览，可从上方工具检查数据配置。")
with st.expander("全部数据与运行工具"):
    render_directory(workspace="数据与运行", prefix="operations_tools")
