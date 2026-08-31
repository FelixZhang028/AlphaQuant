"""Compatibility helpers for trusted, local HTML/JavaScript snippets."""

from __future__ import annotations

from inspect import signature

import streamlit as st
import streamlit.components.v1 as components

_ST_HTML_SUPPORTS_JAVASCRIPT = (
    "unsafe_allow_javascript" in signature(st.html).parameters
)


def javascript_html(
    body: str,
    *,
    fallback_height: int = 0,
    scrolling: bool = False,
) -> None:
    """Render trusted JavaScript on both older and newer Streamlit versions."""
    if _ST_HTML_SUPPORTS_JAVASCRIPT:
        st.html(body, unsafe_allow_javascript=True)
        return
    components.html(body, height=fallback_height, scrolling=scrolling)
