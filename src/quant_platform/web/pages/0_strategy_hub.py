"""Unified workspace for visual, natural-language, and Python strategies."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from quant_platform.web.embedded_page import run_embedded
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("策略工作室")
st.caption("从模板、可视化规则、自然语言或 Python 开始，最终进入同一套回测流程。")

MODES = {
    "模板与积木": ("7_strategy_studio.py", "strategy_visual"),
    "自然语言": ("10_nl_strategy.py", "strategy_natural_language"),
    "Python 策略": ("8_custom_strategy.py", "strategy_python"),
}

mode = st.segmented_control(
    "创建方式",
    list(MODES),
    default="模板与积木",
    key="strategy_workspace_mode",
    label_visibility="collapsed",
    width="stretch",
)

guidance = {
    "模板与积木": "推荐从这里开始：无需编程，可使用模板或组合白名单指标。",
    "自然语言": "用一句话描述想法，由 AI 转成结构化规则，保存前必须人工确认。",
    "Python 策略": "适合需要完全自定义逻辑的用户，保存前会进行安全检查。",
}
st.info(guidance[str(mode)])

filename, embedded_name = MODES[str(mode)]
run_embedded(Path(__file__).with_name(filename), name=embedded_name)
