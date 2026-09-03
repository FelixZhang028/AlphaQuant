"""Friendly Streamlit interface for managing the configured stock universe."""

from __future__ import annotations

from quant_platform.web.embedded_page import is_embedded
from quant_platform.web.theme import inject_global_css

inject_global_css()


import pandas as pd
import streamlit as st

from quant_platform.application.universe_service import (
    UniverseManagementService,
    update_universe_settings,
)
from quant_platform.web.localization import localize_frame

if is_embedded("universe_management"):
    st.subheader("股票池")
else:
    st.title("股票池管理")
st.caption("直接添加、搜索或移除股票。保存后，数据更新和新回测会自动使用当前股票池。")

config_path = "configs/app.yaml"  # 正式版固定配置路径，不再提供侧栏修改入口
try:
    service = UniverseManagementService(config_path)
    settings = service.load()
    description = service.describe_symbols(settings.symbols)
except Exception as exc:
    st.error(f"无法加载股票池：{exc}")
    st.stop()

with_data = int(pd.to_numeric(description["local_rows"], errors="coerce").gt(0).sum())
columns = st.columns(3)
columns[0].metric("股票数量", len(settings.symbols))
columns[1].metric("已有本地行情", with_data)
columns[2].metric("尚未下载行情", len(settings.symbols) - with_data)

display = description.copy()
display["has_local_data"] = pd.to_numeric(display["local_rows"], errors="coerce").gt(0)
st.dataframe(
    localize_frame(display),
    width="stretch",
    hide_index=True,
    column_config={
        "本地开始日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "本地结束日期": st.column_config.DateColumn(format="YYYY-MM-DD"),
    },
)

st.divider()
st.subheader("添加股票")
st.caption("支持六位代码、600519.SH、SH600519；可以用换行、逗号或空格分隔。")
raw_symbols = st.text_area(
    "股票代码",
    placeholder="例如：600519、000001、300750",
    key="universe_symbols_to_add",
)
if st.button("添加代码", type="primary", disabled=not raw_symbols.strip()):
    try:
        updated = service.add_symbols(raw_symbols)
        st.success(f"股票池已保存，现在共有 {len(updated.symbols)} 只股票。")
        st.rerun()
    except Exception as exc:
        st.error(f"添加失败：{exc}")

st.markdown("##### 按名称搜索")
query = st.text_input(
    "输入股票名称或代码",
    placeholder="需要先在数据管理中更新证券主表",
    key="security_master_search",
)
search_results = service.search_security_master(query)
if query and search_results.empty:
    st.info("没有找到匹配股票。请检查名称，或直接在上方输入六位代码。")
elif not search_results.empty:
    labels = {
        str(row["symbol"]): f"{row['symbol']}｜{row['name']}"
        for _, row in search_results.iterrows()
    }
    selected_search_symbols = st.multiselect(
        "搜索结果",
        list(labels),
        format_func=lambda symbol: labels[str(symbol)],
        key="security_master_search_results",
    )
    if st.button(
        "添加选中的股票",
        disabled=not selected_search_symbols,
        key="add_searched_symbols",
    ):
        try:
            service.add_symbols(tuple(selected_search_symbols))
            st.success("选中的股票已经加入股票池。")
            st.rerun()
        except Exception as exc:
            st.error(f"添加失败：{exc}")

st.divider()
st.subheader("移除股票")
name_by_symbol = {
    str(row["symbol"]): (
        f"{row['symbol']}｜{row['name']}" if pd.notna(row["name"]) else str(row["symbol"])
    )
    for _, row in description.iterrows()
}
selected_to_remove = st.multiselect(
    "选择需要移除的股票",
    list(settings.symbols),
    format_func=lambda symbol: name_by_symbol.get(str(symbol), str(symbol)),
    key="universe_symbols_to_remove",
)
confirm_remove = st.checkbox(
    "我确认从股票池移除这些股票（本地历史数据不会被删除）",
    disabled=not selected_to_remove,
)
if st.button(
    "移除选中的股票",
    disabled=not selected_to_remove or not confirm_remove,
    key="remove_universe_symbols",
):
    try:
        service.remove_symbols(selected_to_remove)
        st.success("股票已经从股票池移除，本地历史数据仍然保留。")
        st.rerun()
    except Exception as exc:
        st.error(f"移除失败：{exc}")

with st.expander("股票过滤设置"):
    st.caption("这些设置用于回测时过滤不满足条件的股票，不会删除本地数据。")
    with st.form("universe_filter_form"):
        left, right = st.columns(2)
        with left:
            exclude_st = st.checkbox("排除 ST 股票", value=settings.exclude_st)
            exclude_suspended = st.checkbox("排除停牌股票", value=settings.exclude_suspended)
            minimum_listing_days = st.number_input(
                "最少上市天数",
                min_value=0,
                value=settings.minimum_listing_days,
                step=1,
            )
        with right:
            minimum_history_days = st.number_input(
                "最少历史交易日",
                min_value=1,
                value=settings.minimum_history_days,
                step=1,
            )
            minimum_average_amount = st.number_input(
                "最低20日平均成交额（元）",
                min_value=0.0,
                value=settings.minimum_average_amount,
                step=1_000_000.0,
            )
        save_filters = st.form_submit_button("保存过滤设置", type="primary")
    if save_filters:
        try:
            updated = update_universe_settings(
                settings,
                exclude_st=exclude_st,
                exclude_suspended=exclude_suspended,
                minimum_listing_days=int(minimum_listing_days),
                minimum_history_days=int(minimum_history_days),
                minimum_average_amount=float(minimum_average_amount),
            )
            service.save(updated)
            st.success("股票过滤设置已经保存。")
            st.rerun()
        except Exception as exc:
            st.error(f"保存失败：{exc}")

if with_data < len(settings.symbols):
    st.info("新增股票后，请前往“数据管理”更新配置股票池行情，再运行回测。")
    if st.button("前往数据管理"):
        st.session_state["data_assets_mode"] = "本地数据"
        st.switch_page("pages/13_data_assets.py")
