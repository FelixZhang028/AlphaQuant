"""Strategy editor interaction, stale state and run configuration regression tests."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from quant_platform.application.backtest_service import BacktestRequest
from quant_platform.application.strategy_studio_service import StrategyStudioService

PAGE = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/7_strategy_studio.py"


@pytest.fixture
def studio_app(tmp_path, monkeypatch):
    class Backtests:
        runs_root = tmp_path / "runs"

        def default_request(self):
            return BacktestRequest(
                "rule_builder",
                "test",
                {},
                date(2024, 1, 1),
                date(2024, 12, 31),
                100000.0,
                5,
                "weekly",
            )

        def run(self, request):
            self.requests.append(request)
            if self.fail:
                raise ValueError("测试回测失败")
            return SimpleNamespace(
                result=SimpleNamespace(
                    run_id=f"run-{len(self.requests)}",
                    summary={"cumulative_return": 0.2},
                )
            )

        requests = []
        fail = False

    backtests = Backtests()
    monkeypatch.setattr(
        "quant_platform.application.backtest_service.BacktestService", lambda _: backtests
    )
    app = AppTest.from_file(str(PAGE), default_timeout=20).run()
    assert not app.exception
    return app, backtests, StrategyStudioService(backtests)


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_builder_controls_react_and_changes_invalidate_draft(studio_app):
    app, _, _ = studio_app
    app.number_input(key="builder_count").set_value(3).run()
    assert app.selectbox(key="rule_2_left_indicator")
    app.selectbox(key="rule_0_mode").select("另一个指标").run()
    assert app.selectbox(key="rule_0_right_indicator")
    app.selectbox(key="rule_0_left_indicator").select("移动平均线").run()
    assert app.number_input(key="rule_0_left_window")
    app.button(key="studio_validate").click().run()
    assert app.button(key="studio_save")
    app.number_input(key="builder_top_n").set_value(10).run()
    assert not any(b.key == "studio_save" for b in app.button)
    assert not any(b.label == "使用该策略回测" for b in app.button)
    assert any("条件已修改" in i.value for i in app.info)
    app.text_input(key="builder_name").set_value("").run()
    app.button(key="studio_validate").click().run()
    assert not app.exception
    assert "visual_strategy_draft" not in app.session_state


def test_shared_parameters_and_old_results(studio_app):
    app, backtests, _ = studio_app
    app.date_input(key="studio_start").set_value(date(2024, 2, 1)).run()
    app.number_input(key="studio_cash").set_value(200000.0).run()
    app.button(key="studio_validate").click().run()
    button(app, "使用该策略回测").click().run()
    assert backtests.requests[-1].start_date == date(2024, 2, 1)
    assert backtests.requests[-1].initial_cash == 200000.0
    assert any(m.label == "累计收益" for m in app.metric)
    app.date_input(key="studio_end").set_value(date(2024, 11, 30)).run()
    assert not app.metric
    backtests.fail = True
    button(app, "使用该策略回测").click().run()
    assert "builder_backtest_result" not in app.session_state
    assert not app.metric


def test_templates_save_load_and_preserve_original_version(studio_app):
    app, _, studio = studio_app
    app.button(key="studio_save_template").click().run()
    original = studio.store.list()[0]
    app.button(key="studio_load").click().run()
    assert not app.exception
    assert app.text_input(key="builder_name").value == original.name
    assert app.number_input(key="builder_top_n").value == original.top_n
    app.button(key="studio_validate").click().run()
    from quant_platform.application.strategy_studio_service import StrategyPackage

    loaded = StrategyPackage.from_mapping(app.session_state["visual_strategy_draft"])
    assert loaded.definition == original.definition
    app.number_input(key="builder_top_n").set_value(10).run()
    app.button(key="studio_validate").click().run()
    assert not app.exception
    assert app.button(key="studio_save").label == "保存为新版本"
    app.button(key="studio_save").click().run()
    packages = studio.store.list()
    assert len(packages) == 2
    updated = next(p for p in packages if p.package_id != original.package_id)
    assert updated.top_n == 10
    assert updated.source == f"revision:{original.package_id}"
    assert studio.store.load(original.package_id) == original


def test_template_switch_hides_previous_metrics_and_failure_clears_result(studio_app):
    app, backtests, _ = studio_app
    app.button(key="studio_template_run").click().run()
    assert app.metric
    template_selector = next(s for s in app.selectbox if s.label == "选择一种容易理解的策略")
    template_selector.select(template_selector.options[1]).run()
    assert not app.metric
    backtests.fail = True
    app.button(key="studio_template_run").click().run()
    assert "template_backtest_result" not in app.session_state


def test_saved_strategy_run_uses_shared_settings(studio_app):
    app, backtests, _ = studio_app
    app.button(key="studio_save_template").click().run()
    app.date_input(key="studio_start").set_value(date(2024, 3, 1)).run()
    app.number_input(key="studio_cash").set_value(300000.0).run()
    button(app, "回测已保存策略").click().run()
    assert backtests.requests[-1].start_date == date(2024, 3, 1)
    assert backtests.requests[-1].initial_cash == 300000.0
    app.date_input(key="studio_end").set_value(date(2023, 12, 31)).run()
    assert button(app, "回测已保存策略").disabled
    assert app.button(key="studio_template_run").disabled
