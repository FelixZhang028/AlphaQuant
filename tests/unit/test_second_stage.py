"""Second-stage plans, explainable results, and factor discovery."""

import pytest
from streamlit.testing.v1 import AppTest
from test_guided_research import ROOT, research  # noqa: F401

from quant_platform.application.research_plans import (
    ResearchPlanStore,
    configuration_diff,
    owner_key,
)
from quant_platform.factors.registry import default_registry
from quant_platform.web.factor_library import factor_matches
from quant_platform.web.result_brief import result_brief


def test_immutable_plans_isolate_owners_and_verify_linked_config(tmp_path):
    path = tmp_path / "plans.sqlite3"
    store = ResearchPlanStore(path)
    config = {"app": {"backtest": {"start_date": "2023-01-01"}}, "execution": {"fee": 0.01}}
    one = store.save("alice", "研究", config, {"idea": "低波动"})
    config["execution"]["fee"] = 0.02
    two = store.save("alice", "研究", config, {"idea": "低波动"}, one["plan_id"])
    assert two["revision"] == 2
    assert store.save("alice", "研究", config, {"idea": "低波动"}, one["plan_id"])["revision"] == 2
    assert (
        ResearchPlanStore(path).load("alice", one["plan_id"], 1)["snapshot"]["execution"]["fee"]
        == 0.01
    )
    assert store.list("bob") == []
    with pytest.raises(ValueError):
        store.load("bob", one["plan_id"], 1)
    with pytest.raises(ValueError):
        store.save("bob", "侵入", config, plan_id=one["plan_id"])
    with pytest.raises(ValueError):
        store.link_run("alice", one, "wrong-run", config)
    store.link_run("alice", two, "run-2", config)
    assert store.runs("alice", one["plan_id"], 1) == []
    assert store.runs("alice", one["plan_id"], 2) == ["run-2"]
    assert configuration_diff([one, two])[0]["配置项"] == "execution.fee"


def test_brief_does_not_invent_benchmark_or_oos_success():
    missing = result_brief({"cumulative_return": 0.2, "benchmark_return": float("nan")})
    assert "无法判断" in missing[0][1]
    assert "尚未找到" in missing[2][1]
    losing = result_brief(
        {"cumulative_return": -0.1, "benchmark_return": -0.2, "max_drawdown": -0.25}
    )
    assert "高于基准 10.00 个百分点" in losing[0][1]
    assert "2,500" in losing[1][1]
    assert "单个区间不能证明" in result_brief({}, out_of_sample=True)[2][1]


def test_factor_intents_and_close_filter_state():
    registry = default_registry()
    assert factor_matches(registry.get("volume_ratio_5"), "放量")
    assert factor_matches(registry.get("momentum_20"), "上涨")
    assert not factor_matches(registry.get("momentum_20"), "低波动")
    app = AppTest.from_file(str(ROOT / "src/quant_platform/web/app_pages/9_factor_lab.py")).run(
        timeout=20
    )
    assert not any(b.key == "library_close" for b in app.button)
    app.text_input(key="library_search").set_value("放量").run()
    assert set(app.dataframe[0].value["因子名"]) == {"amount_change_20", "volume_ratio_5"}
    app.session_state[app.dataframe[0].key] = {
        "selection": {"rows": [0], "columns": [], "cells": []}
    }
    app.run()
    assert any(b.key == "library_close" for b in app.button)
    app.text_input(key="library_search").set_value("低波动").run()
    assert not any(b.key == "library_close" for b in app.button)


def test_guided_save_restore_versions_and_run_link(research):  # noqa: F811
    service, repo = research
    app = AppTest.from_file(str(ROOT / "src/quant_platform/web/app.py"), default_timeout=30)
    app.session_state["aq_authenticated_user"] = "alice"
    app.run().switch_page("app_pages/0_strategy_hub.py").run()
    app.radio(key="_guided_idea").set_value("低波动").run()
    app.text_input(key="guided_plan_title").set_value("我的低波动方案").run()
    app.button(key="guided_plan_save").click().run()
    assert not app.exception
    store = ResearchPlanStore("runtime/state/research_plans.sqlite3")
    first = store.list(owner_key("alice"))[0]
    app.number_input(key="_guided_top_n").set_value(6).run()
    app.button(key="guided_plan_save").click().run()
    assert len(store.list(owner_key("alice"))) == 2
    app.button(key="guided_check").click().run()
    next(x for x in app.checkbox if x.key.startswith("guided_confirm_")).check().run()
    app.button(key="guided_run").click().run()
    assert not app.exception
    run = app.session_state["guided_draft"].get("run_id")
    assert run and store.runs(owner_key("alice"), first["plan_id"], 2) == [run]
    # A fresh session must recover the first version from disk, not widget memory.
    fresh = AppTest.from_file(str(ROOT / "src/quant_platform/web/app.py"), default_timeout=30)
    fresh.session_state["aq_authenticated_user"] = "alice"
    fresh.run().switch_page("app_pages/6_run_library.py").run()
    fresh.multiselect(key="plan_compare").set_value([0, 1]).run()
    assert not fresh.exception
    assert any("结果" in frame.value.columns for frame in fresh.dataframe)
    fresh.selectbox(key="plan_version").set_value(1).run()
    fresh.button(key="plan_restore").click().run()
    assert not fresh.exception
    assert fresh.number_input(key="_guided_top_n").value == 5
    assert fresh.radio(key="_guided_idea").value == "低波动"
    assert fresh.button(key="guided_run").disabled
    assert store.load(owner_key("alice"), first["plan_id"], 1)["snapshot"] == first["snapshot"]


def test_generic_restore_rejects_invalid_edit(research):  # noqa: F811
    service, _ = research
    _, snapshot = service.build_engine(service.default_request())
    store = ResearchPlanStore("runtime/state/research_plans.sqlite3")
    store.save(owner_key("alice"), "普通方案", snapshot)
    app = AppTest.from_file(str(ROOT / "src/quant_platform/web/app.py"), default_timeout=30)
    app.session_state["aq_authenticated_user"] = "alice"
    app.run().switch_page("app_pages/6_run_library.py").run()
    app.button(key="plan_restore").click().run()
    app.switch_page("home.py").run()
    next(b for b in app.button if b.label == "检查复用方案").click().run()
    assert not app.exception
    contexts = [
        v for k, v in app.session_state.filtered_state.items() if k.startswith("restored_context_")
    ]
    assert contexts[0].get("request")
    next(t for t in app.text_area if t.label == "策略参数 JSON").set_value("{invalid")
    next(b for b in app.button if b.label == "检查复用方案").click().run()
    assert not app.exception
    contexts = [
        v for k, v in app.session_state.filtered_state.items() if k.startswith("restored_context_")
    ]
    assert not contexts[0].get("request")
    assert any("参数格式或内容无效" in e.value for e in app.error)


@pytest.mark.parametrize("label", ["用本次结果创建验证实验", "继续做样本外验证"])
def test_report_buttons_open_validation_with_selected_run(research, label):  # noqa: F811
    service, _ = research
    completed = service.run(service.default_request())
    run_id = completed.output_dir.name
    app = AppTest.from_file(str(ROOT / "src/quant_platform/web/app.py"), default_timeout=30)
    app.session_state["aq_authenticated_user"] = "alice"
    app.session_state["selected_run"] = run_id
    app.run().switch_page("home.py").run()
    assert not app.exception
    button = next(b for b in app.button if b.label == label)
    assert not button.disabled
    button.click().run()
    assert not app.exception
    assert app.session_state["backtest_workspace_mode"] == "参数优化与稳健性验证"
    assert app.selectbox(key="research_baseline_run_id").value == run_id
