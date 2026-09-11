"""因子实验室页面的交互回归测试。"""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
from streamlit.testing.v1 import AppTest

from quant_platform.factors.evaluation import FactorReport

FACTOR_LAB_PAGE = (
    Path(__file__).parents[2] / "src" / "quant_platform" / "web" / "app_pages" / "9_factor_lab.py"
)


def test_library_filters_and_handoff(tmp_path, monkeypatch):
    config = tmp_path / "configs"
    config.mkdir()
    (config / "app.yaml").write_text("data:\n  repository: runtime/market\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(FACTOR_LAB_PAGE)).run(timeout=20)
    app.selectbox(key="library_source").select("Alpha101").run()
    assert len(app.dataframe[0].value) == 4
    app.text_input(key="library_search").set_value("033").run()
    assert app.dataframe[0].value.iloc[0]["因子名"] == "alpha101_033"
    app.button(key="library_to_eval").click().run()
    assert app.selectbox(key="factor_eval_name").value == "alpha101_033"
    app.button(key="library_to_combine").click().run()
    assert "alpha101_033" in app.multiselect(key="factor_combine_names").value
    app.text_input(key="library_search").set_value("nothing matches").run()
    assert any("没有匹配" in info.value for info in app.info)
    assert not app.exception


def test_evaluation_error_keeps_following_tabs_rendered(tmp_path: Path, monkeypatch) -> None:
    """行情为空时，评估错误不应阻断因子组合和自定义因子的渲染。"""

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text(
        "data:\n  repository: runtime/empty_market\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    app = AppTest.from_file(str(FACTOR_LAB_PAGE)).run(timeout=20)
    app.button(key="factor_eval_run").click().run(timeout=20)

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "因子库",
        "因子评估",
        "因子组合",
        "自定义因子",
    ]
    assert "多因子合成" in [heading.value for heading in app.subheader]
    assert "自定义因子" in [heading.value for heading in app.subheader]
    assert any("评估失败" in error.value for error in app.error)


def test_combination_results_persist_and_changed_settings_block_handoff(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "app.yaml").write_text("data:\n  repository: runtime/market\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    calls = []

    def run_research(repository, components, **config):
        calls.append(config)
        report = FactorReport(
            factor_name="combo",
            display_name="组合",
            horizon=config["horizon"],
            n_groups=5,
            daily_ic=pd.DataFrame(
                {"date": [pd.Timestamp("2025-01-01")], "ic": [0.2], "rank_ic": [0.3]}
            ),
            ic_mean=0.2,
            ic_ir=0.4,
            rank_ic_mean=0.3,
            rank_ic_ir=0.6,
            group_returns=pd.DataFrame(columns=["date", "group", "ret"]),
            group_mean_returns=pd.Series(dtype=float),
            long_short_mean=0.01,
            turnover=pd.DataFrame(columns=["date", "turnover"]),
            turnover_mean=0.2,
            first_half_ic=0.3,
            second_half_ic=0.3,
        )
        return SimpleNamespace(
            weights={f.name: 1 / len(components) for f in components},
            correlation=pd.DataFrame(),
            comparison=pd.DataFrame({"方案": ["等权组合", "我的组合"], "Rank IC": [0.3, 0.3]}),
            reports={"等权组合": report, "我的组合": report},
            spec=[
                {"name": f.name, "weight": 1.0, "clip": True, "missing": "drop"} for f in components
            ],
        )

    monkeypatch.setattr(
        "quant_platform.application.factor_research_service.research_combination", run_research
    )
    app = AppTest.from_file(str(FACTOR_LAB_PAGE)).run(timeout=20)
    app.button(key="factor_combine_run").click().run(timeout=20)
    assert not app.exception
    assert len(calls) == 1
    assert calls[0]["train_end"] < calls[0]["test_start"]
    app.selectbox(key="combo_report_detail").select("我的组合").run(timeout=20)
    assert not app.exception
    assert len(calls) == 1
    assert any(button.key == "factor_to_strategy" for button in app.button)
    app.checkbox(key="factor_winsorize").uncheck().run(timeout=20)
    assert not app.exception
    assert not any(button.key == "factor_to_strategy" for button in app.button)
    assert any("设置已变化" in info.value for info in app.info)
