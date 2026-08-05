"""Chinese navigation entry point for the Streamlit platform."""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="A股量化工作台", layout="wide")

navigation = st.navigation(
    {
        "研究与回测": [
            st.Page("home.py", title="回测工作台", icon="📈", default=True),
            st.Page("pages/2_research.py", title="策略研究", icon="🧪"),
        ],
        "数据与交易": [
            st.Page("pages/1_data_management.py", title="数据管理", icon="🗃️"),
            st.Page("pages/3_risk_management.py", title="风险管理", icon="🛡️"),
            st.Page("pages/4_paper_trading.py", title="模拟交易", icon="🧾"),
        ],
    },
    expanded=True,
)
navigation.run()
