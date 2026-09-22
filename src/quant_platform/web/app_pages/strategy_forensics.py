"""Legacy script entry; external checks now live under credibility audit."""

from __future__ import annotations

import streamlit as st

from quant_platform.web.external_audit import render_external_audit
from quant_platform.web.theme import inject_global_css

inject_global_css()

st.title("可信度审计 · 外部材料")
render_external_audit()
