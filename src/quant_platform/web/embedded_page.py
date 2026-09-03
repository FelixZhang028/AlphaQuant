"""Helpers for composing existing Streamlit tools inside a unified workspace page."""

from __future__ import annotations

import runpy
from pathlib import Path

import streamlit as st

EMBEDDED_PAGE_KEY = "fq_embedded_page"


def is_embedded(name: str) -> bool:
    """Return whether the current script is rendered inside a workspace page."""

    return st.session_state.get(EMBEDDED_PAGE_KEY) == name


def run_embedded(path: str | Path, *, name: str) -> None:
    """Execute a page script while exposing a small, scoped embedding context."""

    previous = st.session_state.get(EMBEDDED_PAGE_KEY)
    st.session_state[EMBEDDED_PAGE_KEY] = name
    try:
        runpy.run_path(str(path), run_name=f"__fq_embedded_{name}__")
    finally:
        if previous is None:
            st.session_state.pop(EMBEDDED_PAGE_KEY, None)
        else:
            st.session_state[EMBEDDED_PAGE_KEY] = previous
