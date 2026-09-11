"""Unified entry for data sources, local datasets, stock pools, and XTick."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pandas as pd
import streamlit as st

from quant_platform.agents_bridge.data_credentials import DataCredentialStore
from quant_platform.web.embedded_page import run_embedded
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("数据资产")
st.caption("统一查看数据源、更新本地数据、维护股票池，并按需调用 XTick 专项接口。")

MODES = {
    "来源对比": None,
    "本地数据": ("1_data_management.py", "data_management"),
    "股票池": ("5_universe_management.py", "universe_management"),
    "XTick 接口": ("11_xtick_data.py", "xtick_data"),
}

mode = st.segmented_control(
    "数据资产区域",
    list(MODES),
    default="来源对比",
    key="data_assets_mode",
    label_visibility="collapsed",
    width="stretch",
)

if mode == "来源对比":
    credentials = DataCredentialStore()
    credentials.load_into_environment()
    rows = [
        {
            "数据源": "XTick",
            "适合场景": "行情、热点、因子与金融指标专项查询",
            "凭证": "Token",
            "当前状态": "已配置" if os.getenv("XTICK_TOKEN") else "未配置",
            "建议": "推荐",
        },
        {
            "数据源": "BaoStock",
            "适合场景": "日线、停牌与历史 ST 状态",
            "凭证": "无需",
            "当前状态": (
                "可用" if importlib.util.find_spec("baostock") is not None else "未安装"
            ),
            "建议": "稳定备用",
        },
        {
            "数据源": "AkShare",
            "适合场景": "证券主表、指数与公开行情",
            "凭证": "无需",
            "当前状态": (
                "可用" if importlib.util.find_spec("akshare") is not None else "未安装"
            ),
            "建议": "公开备用",
        },
        {
            "数据源": "iFinD",
            "适合场景": "机构级行情补充",
            "凭证": "账号与密码",
            "当前状态": (
                "已配置"
                if os.getenv("IFIND_USERNAME") and os.getenv("IFIND_PASSWORD")
                else "未配置"
            ),
            "建议": "按授权选用",
        },
        {
            "数据源": "Tushare",
            "适合场景": "结构化行情与基础数据",
            "凭证": "Token",
            "当前状态": "已配置" if os.getenv("TUSHARE_TOKEN") else "未配置",
            "建议": "按积分选用",
        },
    ]
    st.info(
        "推荐 XTick 作为专项研究入口；本地批量更新仍保留多源回退，"
        "单一数据源不可用时不会阻断全部研究。"
    )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("“推荐”表示界面默认引导，不代表强制使用；你仍可并排比较并自由选择来源。")

    with st.container(border=True):
        st.subheader("使用建议")
        columns = st.columns(3)
        columns[0].markdown("**日常研究**\n\n优先 XTick，必要时与本地行情交叉核对。")
        columns[1].markdown("**批量回测**\n\n使用已落盘并带版本记录的本地数据。")
        columns[2].markdown("**故障回退**\n\nBaoStock、AkShare、PyTDX 按配置顺序补充。")
else:
    target = MODES[str(mode)]
    if target is not None:
        filename, embedded_name = target
        run_embedded(Path(__file__).with_name(filename), name=embedded_name)
