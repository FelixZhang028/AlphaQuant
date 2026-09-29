"""Choose an AI-assisted or manual research workflow."""

import streamlit as st

from quant_platform.web.navigation import render_directory, tool_button

st.title("策略研究")
st.caption("从 AI 分析或自己的策略想法开始，逐步完成回测与验证。")

left, right = st.columns(2)
with left.container(border=True):
    st.subheader(":material/psychology: AI研究员")
    st.write("选择股票，让多个 AI 分析行情与资讯，并查看讨论过程、证据和结论。")
    tool_button("ai", label="打开 AI研究员", primary=True)
    st.caption("已有文字形式的选股规则？可用自然语言创建策略。")
    tool_button("natural")
with right.container(border=True):
    st.subheader(":material/tune: 手动研究")
    st.write("从选股想法、策略模板或自定义规则开始，自主控制参数。")
    tool_button("ideas", label="从选股想法开始")
    tool_button("backtest", label="已有策略，直接回测")

st.subheader("继续完善研究")
for column, key in zip(st.columns(3), ("validation", "factor", "knowledge"), strict=True):
    with column:
        tool_button(key)

with st.expander("全部研究工具"):
    render_directory(workspace="策略研究", prefix="research_tools")
