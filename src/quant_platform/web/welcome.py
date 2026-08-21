"""First-use guide driven by actual local configuration and data state."""

from __future__ import annotations

import streamlit as st

from quant_platform.application.readiness_service import PlatformReadinessService

st.title("开始使用")
st.caption("系统会检查股票池和本地数据，并告诉你下一步应该做什么。检查过程不会联网。")

config_path = st.sidebar.text_input("应用配置", "configs/app.yaml", key="welcome_config_path")
report = PlatformReadinessService(config_path).inspect()

if report.ready_for_backtest:
    st.success(
        f"平台已具备回测条件：{report.symbols_with_sufficient_history}/"
        f"{report.configured_symbols} 只股票拥有足够历史行情。"
    )
else:
    st.warning("首次准备尚未完成。按照下方顺序操作即可，不需要编辑配置文件。")

st.dataframe(report.to_frame(), width="stretch", hide_index=True)

st.divider()

# ── 三步开始：卡片式布局 ──────────────────────────────────────────
st.subheader("三步开始")

pool_col, data_col, backtest_col = st.columns(3)

with pool_col:
    with st.container(border=True):
        st.markdown("### 📋 设置股票池")
        st.write("添加你想研究的股票，也可以使用当前默认股票池。")
        st.button(
            "打开股票池管理",
            key="welcome_open_pool",
            on_click=lambda: st.switch_page("pages/5_universe_management.py"),
            use_container_width=True,
        )

with data_col:
    with st.container(border=True):
        st.markdown("### 🗃️ 准备行情")
        st.write("下载证券名称、股票日线和基准行情，并检查覆盖率。")
        st.button(
            "打开数据管理",
            key="welcome_open_data",
            on_click=lambda: st.switch_page("pages/1_data_management.py"),
            use_container_width=True,
        )

with backtest_col:
    with st.container(border=True):
        st.markdown("### 📈 运行回测")
        st.write("数据达到最少历史天数后，即可选择策略并运行。")
        st.button(
            "进入单次回测与复盘",
            key="welcome_open_backtest",
            on_click=lambda: st.switch_page("home.py"),
            disabled=not report.ready_for_backtest,
            use_container_width=True,
        )

with st.expander("如果检查没有通过"):
    st.markdown(
        """
- **股票池为空**：前往"股票池管理"，输入六位股票代码并保存。
- **没有股票行情**：前往"数据管理"，勾选"更新配置股票池行情"。
- **历史天数不足**：把数据更新的开始日期向前调整，再次更新。
- **证券主表缺失**：仍可通过代码添加股票，但按名称搜索前需要更新证券主表。
- **网络更新失败**：检查网络或代理后重试；已经成功的数据不会被删除。
"""
    )
