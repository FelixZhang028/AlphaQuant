"""Chinese navigation entry point for the Streamlit platform."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from quant_platform.application.readiness_service import platform_needs_onboarding

LOGO_PATH = Path(__file__).parent / "assets" / "alphaquant-logo.png"

st.set_page_config(
    page_title="AlphaQuant量化工作台", page_icon=str(LOGO_PATH), layout="wide"
)
st.logo(str(LOGO_PATH), size="large", icon_image=str(LOGO_PATH))

needs_onboarding = platform_needs_onboarding()

navigation = st.navigation(
    {
        "开始": [
            st.Page(
                "welcome.py",
                title="开始使用",
                icon="👋",
                default=needs_onboarding,
            ),
        ],
        "研究与回测": [
            st.Page(
                "pages/7_strategy_studio.py",
                title="零代码策略工作台",
                icon="🧩",
            ),
            st.Page(
                "home.py",
                title="单次回测与复盘",
                icon="📈",
                default=not needs_onboarding,
            ),
            st.Page(
                "pages/2_research.py",
                title="参数优化与稳健性验证",
                icon="🧪",
            ),
            st.Page("pages/6_run_library.py", title="回测记录库", icon="🗂️"),
        ],
        "数据与交易": [
            st.Page("pages/1_data_management.py", title="数据管理", icon="🗃️"),
            st.Page("pages/3_risk_management.py", title="风险管理", icon="🛡️"),
            st.Page("pages/4_paper_trading.py", title="模拟交易", icon="🧾"),
        ],
        "设置": [
            st.Page("pages/5_universe_management.py", title="股票池管理", icon="📋"),
        ],
    },
    expanded=True,
)
navigation.run()
