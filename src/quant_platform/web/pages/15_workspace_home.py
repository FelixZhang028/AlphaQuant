"""Authenticated research home for choosing and resuming work."""

from __future__ import annotations

import streamlit as st

from quant_platform.agents_bridge.prior_knowledge import PriorKnowledgeStore
from quant_platform.application.backtest_service import BacktestService
from quant_platform.application.readiness_service import PlatformReadinessService
from quant_platform.web.run_labels import format_run_label
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.html(
    """
    <span class="aq-workspace-home-marker" aria-hidden="true"></span>
    <style>
    html:has(.aq-workspace-home-marker) [data-testid="stMain"] {
        background:
            radial-gradient(circle at 84% 4%, rgba(124, 92, 255, .11), transparent 34rem),
            radial-gradient(circle at 15% 34%, rgba(65, 169, 255, .07), transparent 28rem),
            #05070d !important;
    }

    .st-key-aq_home_choice_ai,
    .st-key-aq_home_choice_strategy,
    .st-key-aq_home_quick_data,
    .st-key-aq_home_quick_strategy,
    .st-key-aq_home_quick_validate {
        position: relative !important;
        isolation: isolate;
        cursor: pointer;
        --aq-card-accent: 91, 168, 255;
    }
    .st-key-aq_home_choice_strategy,
    .st-key-aq_home_quick_strategy {
        --aq-card-accent: 147, 112, 255;
    }
    .st-key-aq_home_quick_data {
        --aq-card-accent: 45, 212, 191;
    }
    .st-key-aq_home_quick_validate {
        --aq-card-accent: 246, 184, 88;
    }

    .st-key-aq_home_choice_ai,
    .st-key-aq_home_choice_strategy,
    .st-key-aq_home_quick_data,
    .st-key-aq_home_quick_strategy,
    .st-key-aq_home_quick_validate {
        overflow: hidden;
        border-color: rgba(var(--aq-card-accent), .28) !important;
        background:
            linear-gradient(135deg, rgba(var(--aq-card-accent), .10), transparent 56%),
            rgba(10, 15, 25, .90) !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, .035);
        transition:
            transform .18s ease,
            border-color .18s ease,
            box-shadow .18s ease,
            background .18s ease;
    }
    .st-key-aq_home_choice_ai::before,
    .st-key-aq_home_choice_strategy::before,
    .st-key-aq_home_quick_data::before,
    .st-key-aq_home_quick_strategy::before,
    .st-key-aq_home_quick_validate::before {
        content: "";
        position: absolute;
        top: 0;
        left: 1rem;
        right: 1rem;
        height: 2px;
        background: linear-gradient(90deg, rgb(var(--aq-card-accent)), transparent);
        opacity: .76;
    }
    .st-key-aq_home_choice_ai::after,
    .st-key-aq_home_choice_strategy::after,
    .st-key-aq_home_quick_data::after,
    .st-key-aq_home_quick_strategy::after,
    .st-key-aq_home_quick_validate::after {
        content: "↗";
        position: absolute;
        top: 1rem;
        right: 1.15rem;
        z-index: 2;
        color: rgba(var(--aq-card-accent), .72);
        font-size: 1.05rem;
        line-height: 1;
        pointer-events: none;
        transition: transform .18s ease, color .18s ease;
    }
    .st-key-aq_home_choice_ai:hover,
    .st-key-aq_home_choice_strategy:hover,
    .st-key-aq_home_quick_data:hover,
    .st-key-aq_home_quick_strategy:hover,
    .st-key-aq_home_quick_validate:hover {
        transform: translateY(-2px);
        border-color: rgba(var(--aq-card-accent), .72) !important;
        background:
            linear-gradient(135deg, rgba(var(--aq-card-accent), .16), transparent 60%),
            rgba(12, 18, 30, .96) !important;
        box-shadow: 0 14px 34px rgba(0, 0, 0, .24), 0 0 24px rgba(var(--aq-card-accent), .07);
    }
    .st-key-aq_home_choice_ai:hover::after,
    .st-key-aq_home_choice_strategy:hover::after,
    .st-key-aq_home_quick_data:hover::after,
    .st-key-aq_home_quick_strategy:hover::after,
    .st-key-aq_home_quick_validate:hover::after {
        color: rgb(var(--aq-card-accent));
        transform: translate(2px, -2px);
    }
    .st-key-aq_home_choice_ai:has(a:focus-visible),
    .st-key-aq_home_choice_strategy:has(a:focus-visible),
    .st-key-aq_home_quick_data:has(a:focus-visible),
    .st-key-aq_home_quick_strategy:has(a:focus-visible),
    .st-key-aq_home_quick_validate:has(a:focus-visible) {
        outline: 2px solid rgb(var(--aq-card-accent));
        outline-offset: 3px;
    }

    .st-key-aq_home_choice_ai [data-testid="stIconMaterial"],
    .st-key-aq_home_choice_strategy [data-testid="stIconMaterial"],
    .st-key-aq_home_quick_data [data-testid="stIconMaterial"],
    .st-key-aq_home_quick_strategy [data-testid="stIconMaterial"],
    .st-key-aq_home_quick_validate [data-testid="stIconMaterial"],
    .st-key-aq_home_choice_ai [role="img"],
    .st-key-aq_home_choice_strategy [role="img"],
    .st-key-aq_home_quick_data [role="img"],
    .st-key-aq_home_quick_strategy [role="img"],
    .st-key-aq_home_quick_validate [role="img"] {
        color: rgb(var(--aq-card-accent)) !important;
    }

    .st-key-aq_home_choice_ai [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]),
    .st-key-aq_home_choice_strategy [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]),
    .st-key-aq_home_quick_data [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]),
    .st-key-aq_home_quick_strategy [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]),
    .st-key-aq_home_quick_validate [data-testid="stElementContainer"]:has(> [data-testid="stPageLink"]) {
        position: absolute !important;
        inset: 0 !important;
        z-index: 5 !important;
        width: auto !important;
        min-width: 0 !important;
        height: auto !important;
        margin: 0 !important;
    }
    .st-key-aq_home_choice_ai [data-testid="stPageLink"],
    .st-key-aq_home_choice_strategy [data-testid="stPageLink"],
    .st-key-aq_home_quick_data [data-testid="stPageLink"],
    .st-key-aq_home_quick_strategy [data-testid="stPageLink"],
    .st-key-aq_home_quick_validate [data-testid="stPageLink"],
    .st-key-aq_home_choice_ai [data-testid="stPageLink"] > div,
    .st-key-aq_home_choice_strategy [data-testid="stPageLink"] > div,
    .st-key-aq_home_quick_data [data-testid="stPageLink"] > div,
    .st-key-aq_home_quick_strategy [data-testid="stPageLink"] > div,
    .st-key-aq_home_quick_validate [data-testid="stPageLink"] > div,
    .st-key-aq_home_choice_ai [data-testid="stPageLink"] a,
    .st-key-aq_home_choice_strategy [data-testid="stPageLink"] a,
    .st-key-aq_home_quick_data [data-testid="stPageLink"] a,
    .st-key-aq_home_quick_strategy [data-testid="stPageLink"] a,
    .st-key-aq_home_quick_validate [data-testid="stPageLink"] a {
        width: 100% !important;
        height: 100% !important;
        margin: 0 !important;
    }
    .st-key-aq_home_choice_ai [data-testid="stPageLink"] a,
    .st-key-aq_home_choice_strategy [data-testid="stPageLink"] a,
    .st-key-aq_home_quick_data [data-testid="stPageLink"] a,
    .st-key-aq_home_quick_strategy [data-testid="stPageLink"] a,
    .st-key-aq_home_quick_validate [data-testid="stPageLink"] a {
        opacity: 0 !important;
    }

    .st-key-aq_home_metric_pool,
    .st-key-aq_home_metric_history,
    .st-key-aq_home_metric_knowledge,
    .st-key-aq_home_metric_records {
        --aq-metric-accent: 45, 212, 191;
    }
    .st-key-aq_home_metric_history { --aq-metric-accent: 80, 210, 150; }
    .st-key-aq_home_metric_knowledge { --aq-metric-accent: 91, 168, 255; }
    .st-key-aq_home_metric_records { --aq-metric-accent: 147, 112, 255; }
    .st-key-aq_home_metric_pool,
    .st-key-aq_home_metric_history,
    .st-key-aq_home_metric_knowledge,
    .st-key-aq_home_metric_records {
        border-color: rgba(var(--aq-metric-accent), .24) !important;
        background: linear-gradient(145deg, rgba(var(--aq-metric-accent), .10), rgba(10, 16, 25, .88)) !important;
        box-shadow: inset 3px 0 0 rgba(var(--aq-metric-accent), .72);
    }
    .st-key-aq_home_metric_pool [data-testid="stMetricValue"],
    .st-key-aq_home_metric_history [data-testid="stMetricValue"],
    .st-key-aq_home_metric_knowledge [data-testid="stMetricValue"],
    .st-key-aq_home_metric_records [data-testid="stMetricValue"],
    .st-key-aq_home_metric_pool [data-testid="stMetricValue"] *,
    .st-key-aq_home_metric_history [data-testid="stMetricValue"] *,
    .st-key-aq_home_metric_knowledge [data-testid="stMetricValue"] *,
    .st-key-aq_home_metric_records [data-testid="stMetricValue"] * {
        color: rgb(var(--aq-metric-accent)) !important;
    }

    @media (prefers-reduced-motion: reduce) {
        .st-key-aq_home_choice_ai,
        .st-key-aq_home_choice_strategy,
        .st-key-aq_home_quick_data,
        .st-key-aq_home_quick_strategy,
        .st-key-aq_home_quick_validate {
            transform: none !important;
            transition: none !important;
        }
    }
    </style>
    """
)

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
with ai_column.container(key="aq_home_choice_ai", border=True, height="stretch"):
    st.markdown("### :material/psychology: AI研究员")
    st.write("由 AI 带你拆解问题、调用数据，并结合先验知识形成可验证的研究结论。")
    st.caption("适合刚开始量化研究，或希望快速梳理研究思路。")
    st.page_link(
        "pages/8_agent_lab.py",
        label="打开 AI研究员",
        width="stretch",
    )
with strategy_column.container(
    key="aq_home_choice_strategy", border=True, height="stretch"
):
    st.markdown("### :material/widgets: 策略工作室")
    st.write("自主构建策略与因子，设置参数，并进入回测与稳健性验证流程。")
    st.caption("适合已有研究想法，希望完整控制策略逻辑和验证过程。")
    st.page_link(
        "pages/0_strategy_hub.py",
        label="打开策略工作室",
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
        "aq_home_quick_data",
    ),
    (
        "02",
        "构建研究",
        "创建策略，或从因子实验开始。",
        "pages/0_strategy_hub.py",
        ":material/widgets:",
        "aq_home_quick_strategy",
    ),
    (
        "03",
        "运行验证",
        "检查收益、风险和样本外稳健性。",
        "home.py",
        ":material/candlestick_chart:",
        "aq_home_quick_validate",
    ),
)
for column, (index, title, description, page, icon, key) in zip(
    st.columns(3), quick_steps, strict=True
):
    with column.container(key=key, border=True, height="stretch"):
        st.caption(index)
        st.markdown(f"**{icon} {title}**")
        st.caption(description)
        st.page_link(page, label=f"打开{title}", width="stretch")

st.subheader("工作区概览")
overview_columns = st.columns(4)
with overview_columns[0].container(key="aq_home_metric_pool", border=True):
    st.metric(
        "股票池",
        readiness.configured_symbols if readiness is not None else "—",
    )
with overview_columns[1].container(key="aq_home_metric_history", border=True):
    st.metric(
        "数据量",
        readiness.symbols_with_sufficient_history if readiness is not None else "—",
    )
with overview_columns[2].container(key="aq_home_metric_knowledge", border=True):
    st.metric("先验知识", knowledge_count)
with overview_columns[3].container(key="aq_home_metric_records", border=True):
    st.metric("研究记录", len(recent_runs))

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
