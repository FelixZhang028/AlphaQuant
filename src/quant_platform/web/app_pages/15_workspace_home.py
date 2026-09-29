"""A small task-oriented entry to the research workspace."""

import streamlit as st

from quant_platform.application.backtest_service import BacktestService
from quant_platform.web.navigation import open_result, tool_button
from quant_platform.web.run_labels import format_run_label

st.title("首页")
st.caption("从一个问题开始，或继续最近的研究。")
for column, title, description, target in zip(
    st.columns(3),
    ("验证策略想法", "检查外部策略", "查看研究结果"),
    (
        "用 AI 分析股票，或构建策略并运行回测。",
        "核查外部收益材料与策略证据。",
        "查看已有回测、可信度与验证记录。",
    ),
    ("app_pages/17_strategy_research.py", None, "app_pages/18_my_research.py"),
    strict=True,
):
    with column.container(border=True):
        st.subheader(title)
        st.write(description)
        if target:
            st.page_link(target, label=title, width="stretch")
        else:
            tool_button("external", label="检查外部策略", prefix="home")

st.subheader("最近研究")
try:
    service = BacktestService("configs/app.yaml")
    records = service.run_store.list_records(successful_only=True)
    names = {item.plugin_name: item.display_name for item in service.available_strategies()}
except Exception:
    records = []
    names = {}
    st.info("暂时无法读取研究记录，可从上方入口检查已有研究。")

if records:
    st.button("继续上次研究", type="primary", on_click=open_result, args=(records[0].run_id,))
    for record in records[:3]:
        with st.container(border=True):
            st.write(format_run_label(record, names))
            st.button(
                "查看结果",
                key=f"home_run_{record.run_id}",
                on_click=open_result,
                args=(record.run_id,),
            )
else:
    st.info("还没有已完成的回测。从“验证策略想法”开始第一次研究。")
