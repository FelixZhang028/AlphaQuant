"""Taxonomy coverage and research intent filtering regression tests."""

from dataclasses import replace

from streamlit.testing.v1 import AppTest

from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.builtins import builtin_factors
from quant_platform.factors.taxonomy import (
    ALPHA_CLASSIFICATIONS,
    INTENT_TERMS,
    classify_factor,
    factor_intents,
)


def test_every_available_factor_has_reviewed_metadata():
    alphas = alpha101_factors()
    assert set(ALPHA_CLASSIFICATIONS) == {f.name for f in alphas}
    for factor in [*alphas, *builtin_factors()]:
        info = classify_factor(factor)
        assert info.category != "未分类"
        assert info.intents and info.rationale
        assert set(info.intents) <= set(INTENT_TERMS)
    # Directional intent is conservative: volume correlation isn't a volume surge.
    for factor in alphas:
        assert not {"关注放量", "偏好低波动"}.intersection(factor_intents(factor))
    assert ALPHA_CLASSIFICATIONS["alpha101_006"].category == "量价关系"
    assert ALPHA_CLASSIFICATIONS["alpha101_033"].category == "反转与偏离"
    assert "研究波动变化" in ALPHA_CLASSIFICATIONS["alpha101_040"].intents
    assert ALPHA_CLASSIFICATIONS["alpha101_096"].category == "量价关系"


def test_unreviewed_or_custom_formula_does_not_inherit_name_labels():
    factor = alpha101_factors()[0]
    unknown = replace(factor, name="alpha101_999")
    assert classify_factor(unknown).category == "未分类"
    assert not factor_intents(unknown)
    assert not factor_intents(replace(factor, source="自定义"))


def test_intent_union_cross_filters_search_and_detail_reset():
    app = AppTest.from_string("""
from quant_platform.factors.alpha101 import alpha101_factors
from quant_platform.factors.builtins import builtin_factors
from quant_platform.web.factor_library import render_factor_library
render_factor_library({f.name:f for f in [*alpha101_factors(), *builtin_factors()]}, has_data=False)
""").run()
    assert not app.exception
    assert len(app.dataframe[0].value) == 92
    app.multiselect(key="library_intents").set_value(["研究量价关系", "寻找短期超跌"]).run()
    expected = {
        f.name
        for f in [*alpha101_factors(), *builtin_factors()]
        if {"研究量价关系", "寻找短期超跌"}.intersection(factor_intents(f))
    }
    assert set(app.dataframe[0].value["因子名"]) == expected
    app.selectbox(key="library_source").select("Alpha101").run()
    app.selectbox(key="library_category").select("反转与偏离").run()
    app.text_input(key="library_search").set_value("033").run()
    assert list(app.dataframe[0].value["因子名"]) == ["alpha101_033"]
    app.session_state[app.dataframe[0].key] = {
        "selection": {"rows": [0], "columns": [], "cells": []}
    }
    app.run()
    assert any("分类依据" in c.value for c in app.caption)
    app.multiselect(key="library_intents").set_value(["关注放量"]).run()
    assert any("没有匹配" in i.value for i in app.info)
    assert not any(b.key == "library_close" for b in app.button)
    app.multiselect(key="library_intents").set_value([]).run()
    assert list(app.dataframe[0].value["因子名"]) == ["alpha101_033"]
    assert not any(b.key == "library_close" for b in app.button)
    assert not app.exception
