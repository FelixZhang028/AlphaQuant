"""Research records with direct access to audits and AI work."""

from pathlib import Path

import streamlit as st

from quant_platform.web.embedded_page import run_embedded
from quant_platform.web.navigation import tool_button

st.title("我的研究")
st.caption("查找和对比已有结果，继续验证，或查看判断依据。")
for column, key in zip(st.columns(3), ("audit", "external", "ai"), strict=True):
    with column:
        tool_button(key, label="继续 AI 研究" if key == "ai" else None, prefix="my_research")
run_embedded(Path(__file__).with_name("6_run_library.py"), name="my_research")
