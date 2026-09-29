"""Exercise workspace entry points and retained expert controls."""

import pytest
from streamlit.testing.v1 import AppTest
from test_guided_research import ROOT, research  # noqa: F401

from quant_platform.web.navigation import WORKSPACES


def app():
    result = AppTest.from_file(ROOT / "src/quant_platform/web/app.py", default_timeout=30)
    result.session_state["aq_authenticated_user"] = "test-user"
    return result.run()


@pytest.mark.parametrize("workspace", WORKSPACES)
def test_workspaces_render(workspace):
    result = app().switch_page(workspace.path).run()
    assert not result.exception
    assert result.title[0].value == workspace.title


def test_search_and_external_entry_select_correct_mode():
    result = app()
    result.text_input(key="all_tools_search").set_value("Python").run()
    assert result.button(key="all_tools_python")
    assert not any(b.key == "all_tools_ai" for b in result.button)
    result.button(key="home_external").click().run()
    assert not result.exception
    assert result.session_state["audit_subject"] == "外部材料"


def test_research_ai_and_backtest_controls(research):  # noqa: F811
    result = app().switch_page("app_pages/17_strategy_research.py").run()
    assert result.button(key="workspace_ai").label == "打开 AI研究员"
    result.button(key="workspace_backtest").click().run()
    assert not result.exception
    # AppTest needs its target synchronized after a programmatic page switch.
    result.switch_page("home.py").run()
    advanced = next(e for e in result.expander if e.label == "高级设置：策略参数与组合规则")
    assert not advanced.proto.expanded
    next(w for w in result.number_input if w.label == "最大持仓数量").set_value(7)
    result.selectbox(key="backtest_allocation").set_value("inverse_volatility")
    next(b for b in result.button if b.label == "检查数据并准备回测").click().run()
    assert not result.exception
    request = result.session_state["pending_backtest_request"]
    assert request.top_n == 7
    assert request.portfolio_method == "inverse_volatility"


def test_home_result_opens_matching_audit(research):  # noqa: F811
    service, _ = research
    completed = service.run(service.default_request())
    result = app()
    result.button(key=f"home_run_{completed.output_dir.name}").click().run()
    assert not result.exception
    assert any(m.label == "可信度评级" for m in result.metric)
    assert any(h.value == "策略与基准走势" for h in result.subheader)
    result.switch_page("home.py").run()
    result.button(key="result_audit").click().run()
    assert not result.exception
    assert result.selectbox(key="audit_report_run").value == completed.output_dir.name
