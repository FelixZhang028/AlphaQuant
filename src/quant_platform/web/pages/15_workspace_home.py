"""Authenticated research home for choosing and resuming work."""

from __future__ import annotations

import streamlit as st

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.readiness_service import PlatformReadinessService
from quant_platform.web.run_labels import format_run_label
from quant_platform.web.theme import inject_global_css

inject_global_css()

CONFIG_PATH = "configs/app.yaml"
username = str(st.session_state.get("aq_authenticated_user") or "研究者")

try:
    readiness = PlatformReadinessService(CONFIG_PATH).inspect()
except Exception:  # noqa: BLE001 - 首页摘要失败不应阻断其它研究入口
    readiness = None

try:
    backtests = BacktestService(CONFIG_PATH)
    recent_runs = backtests.run_store.list_records(successful_only=True)
    strategy_names = {
        metadata.plugin_name: metadata.display_name
        for metadata in backtests.available_strategies()
    }
except Exception:  # noqa: BLE001 - 首页摘要失败不应阻断其它研究入口
    recent_runs = []
    strategy_names = {}

try:
    knowledge_count = len(PriorKnowledgeStore().list())
except Exception:  # noqa: BLE001 - 首页摘要失败不应阻断其它研究入口
    knowledge_count = 0

heading, resume = st.columns([4, 1], vertical_alignment="bottom")
with heading:
    st.title("首页")
    st.caption(f"欢迎回来，{username}。选择一种研究方式，或继续最近的工作。")
with resume:
    if recent_runs:
        if st.button(
            "继续上次研究",
            type="primary",
            icon=":material/arrow_forward:",
            width="stretch",
        ):
            st.session_state["selected_run"] = recent_runs[0].run_id
            st.switch_page("home.py")
    elif st.button(
        "开始第一次研究",
        type="primary",
        icon=":material/arrow_forward:",
        width="stretch",
    ):
        st.switch_page("pages/8_agent_lab.py")

st.subheader("选择研究方式")
st.caption("两条路径可以随时切换，研究结果会统一保存在工作台中。")
ai_column, strategy_column = st.columns(2, gap="large")
with ai_column.container(border=True, height="stretch"):
    st.markdown("### :material/psychology: AI研究员")
    st.write("由 AI 带你拆解问题、调用数据，并结合先验知识形成可验证的研究结论。")
    st.caption("适合刚开始量化研究，或希望快速梳理研究思路。")
    st.page_link(
        "pages/8_agent_lab.py",
        label="让 AI 带我研究",
        icon=":material/auto_awesome:",
        width="stretch",
    )
with strategy_column.container(border=True, height="stretch"):
    st.markdown("### :material/widgets: 策略工作室")
    st.write("自主构建策略与因子，设置参数，并进入回测与稳健性验证流程。")
    st.caption("适合已有研究想法，希望完整控制策略逻辑和验证过程。")
    st.page_link(
        "pages/0_strategy_hub.py",
        label="自己构建策略",
        icon=":material/build:",
        width="stretch",
    )

st.subheader("快速开始")
quick_steps = (
    (
        "01",
        "准备数据",
        "选择数据源并维护股票池。",
        "pages/13_data_assets.py",
        ":material/database:",
    ),
    (
        "02",
        "构建研究",
        "创建策略，或从因子实验开始。",
        "pages/0_strategy_hub.py",
        ":material/widgets:",
    ),
    (
        "03",
        "运行验证",
        "检查收益、风险和样本外稳健性。",
        "home.py",
        ":material/candlestick_chart:",
    ),
)
for column, (index, title, description, page, icon) in zip(
    st.columns(3), quick_steps, strict=True
):
    with column.container(border=True, height="stretch"):
        st.caption(index)
        st.markdown(f"**{title}**")
        st.caption(description)
        st.page_link(page, label="打开", icon=icon, width="stretch")

st.subheader("工作区概览")
overview_columns = st.columns(4)
overview_columns[0].metric(
    "股票池",
    readiness.configured_symbols if readiness is not None else "—",
    border=True,
)
overview_columns[1].metric(
    "数据充足",
    readiness.symbols_with_sufficient_history if readiness is not None else "—",
    border=True,
)
overview_columns[2].metric("先验知识", knowledge_count, border=True)
overview_columns[3].metric("研究记录", len(recent_runs), border=True)

st.subheader("最近研究")
if not recent_runs:
    with st.container(border=True):
        st.write("还没有回测记录。你可以先让 AI 帮你梳理思路，或直接构建一个策略。")
else:
    for record in recent_runs[:3]:
        record_copy, record_action = st.columns([5, 1], vertical_alignment="center")
        with record_copy:
            st.markdown(f"**{format_run_label(record, strategy_names)}**")
            st.caption("已完成回测，可继续查看结果并开展稳健性验证。")
        with record_action:
            if st.button(
                "查看结果",
                key=f"workspace_home_run_{record.run_id}",
                width="stretch",
            ):
                st.session_state["selected_run"] = record.run_id
                st.switch_page("home.py")

