"""Chinese navigation entry point for the Streamlit platform."""

from __future__ import annotations

from html import escape
from pathlib import Path

import streamlit as st

from quant_platform.web.theme import inject_global_css

LOGO_PATH = Path(__file__).parent / "assets" / "fellowquant-logo.png"

st.set_page_config(
    page_title="FellowQuant量化工作台",
    page_icon=str(LOGO_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
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
            st.Page(
                "pages/11_xtick_data.py", title="XTick 数据服务", icon=":material/api:"
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

# Shared page state must be initialized in the entrypoint so every page sees
# the same value during Streamlit's same-session navigation.
st.session_state.setdefault("aq_authenticated_user", None)

# Place a native Streamlit page link over the sidebar logo. This keeps the
# navigation inside the current session instead of reloading the app root.
st.markdown(
    """
    <style>
    .st-key-aq_logo_home_link {
      position: fixed !important;
      top: .45rem !important;
      left: .7rem !important;
      z-index: 100000 !important;
      width: 150px !important;
      height: 54px !important;
      overflow: hidden !important;
      opacity: 0 !important;
      pointer-events: auto !important;
    }
    .st-key-aq_logo_home_link a {
      display: block !important;
      width: 100% !important;
      height: 100% !important;
    }
    [data-testid="stSidebarContent"] {
      padding-bottom: 5.9rem !important;
    }
    .st-key-aq_sidebar_account {
      position: fixed !important;
      left: .75rem !important;
      bottom: 1.25rem !important;
      z-index: 100001 !important;
      width: calc(var(--st-sidebar-width, 16rem) - 1.5rem) !important;
      max-width: calc(100vw - 1.5rem) !important;
    }
    .st-key-aq_sidebar_account [data-testid="stMarkdownContainer"] > div {
      display: flex;
      align-items: center;
      gap: .7rem;
      padding: .85rem .55rem .15rem;
      border-top: 1px solid rgba(255, 255, 255, .12);
    }
    .aq-sidebar-account__avatar {
      display: grid;
      place-items: center;
      width: 2rem;
      height: 2rem;
      flex: 0 0 2rem;
      color: #7ec8ff;
      background: rgba(86, 134, 254, .14);
      border-radius: 50%;
    }
    .aq-sidebar-account__avatar svg {
      width: 1rem;
      height: 1rem;
    }
    .aq-sidebar-account__copy {
      min-width: 0;
      display: grid;
      gap: .14rem;
    }
    .aq-sidebar-account__name {
      overflow: hidden;
      color: #f0f4fa;
      font-size: .82rem;
      font-weight: 500;
      line-height: 1.2;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .aq-sidebar-account__state {
      display: flex;
      align-items: center;
      gap: .35rem;
      color: #8f98a5;
      font-size: .68rem;
      line-height: 1.2;
    }
    .aq-sidebar-account__state::before {
      content: "";
      width: .4rem;
      height: .4rem;
      background: #43c58a;
      border-radius: 50%;
      box-shadow: 0 0 0 3px rgba(67, 197, 138, .1);
    }
    </style>
    """,
    unsafe_allow_html=True,
)
with st.sidebar:
    with st.container(key="aq_logo_home_link"):
        st.page_link("welcome.py", label="返回欢迎页")
    authenticated_user = st.session_state.get("aq_authenticated_user")
    if authenticated_user:
        safe_username = escape(str(authenticated_user))
        with st.container(key="aq_sidebar_account"):
            st.markdown(
                f"""
                <div role="status" aria-label="用户 {safe_username} 已登录">
                  <span class="aq-sidebar-account__avatar" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none">
                      <circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.8"/>
                      <path d="M5.5 19c.7-3.3 3.1-5 6.5-5s5.8 1.7 6.5 5"
                            stroke="currentColor" stroke-width="1.8"
                            stroke-linecap="round"/>
                    </svg>
                  </span>
                  <span class="aq-sidebar-account__copy">
                    <span class="aq-sidebar-account__name">{safe_username}</span>
                    <span class="aq-sidebar-account__state">已登录</span>
                  </span>
                </div>
                """,
                unsafe_allow_html=True,
            )
navigation.run()
