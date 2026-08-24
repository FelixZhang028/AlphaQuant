"""Chinese navigation entry point for the Streamlit platform."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from quant_platform.web.theme import inject_global_css

LOGO_PATH = Path(__file__).parent / "assets" / "alphaquant-logo.png"

st.set_page_config(
    page_title="AlphaQuant量化工作台",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="collapsed",
)
st.logo(str(LOGO_PATH), size="large", icon_image=str(LOGO_PATH))

inject_global_css()

navigation = st.navigation(
    {
        "开始": [
            st.Page(
                "welcome.py",
                title="开始使用",
                icon=":material/flag:",
                default=True,
            ),
        ],
        "策略研究": [
            st.Page(
                "pages/0_strategy_hub.py",
                title="策略创作中心",
                icon=":material/hub:",
            ),
            st.Page(
                "pages/10_nl_strategy.py",
                title="自然语言建策略",
                icon=":material/chat:",
            ),
            st.Page(
                "pages/7_strategy_studio.py",
                title="零代码策略工作台",
                icon=":material/widgets:",
            ),
            st.Page(
                "pages/8_custom_strategy.py",
                title="自定义策略（Python）",
                icon=":material/code:",
            ),
            st.Page(
                "pages/9_factor_lab.py",
                title="因子研究室",
                icon=":material/science:",
            ),
            st.Page(
                "pages/8_agent_lab.py",
                title="智能体分析台",
                icon=":material/psychology:",
            ),
        ],
        "回测与验证": [
            st.Page(
                "home.py",
                title="单次回测与复盘",
                icon=":material/candlestick_chart:",
            ),
            st.Page(
                "pages/2_research.py",
                title="参数优化与稳健性验证",
                icon=":material/tune:",
            ),
            st.Page("pages/6_run_library.py", title="回测记录库", icon=":material/history:"),
        ],
        "数据与交易": [
            st.Page(
                "pages/1_data_management.py", title="数据管理", icon=":material/database:"
            ),
            st.Page("pages/3_risk_management.py", title="风险管理", icon=":material/shield:"),
            st.Page(
                "pages/4_paper_trading.py",
                title="模拟交易",
                icon=":material/account_balance:",
            ),
        ],
        "设置": [
            st.Page(
                "pages/5_universe_management.py",
                title="股票池管理",
                icon=":material/list_alt:",
            ),
        ],
    },
    expanded=True,
)
navigation.run()
