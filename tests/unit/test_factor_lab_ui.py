"""因子实验室页面的交互回归测试。"""

from pathlib import Path

from streamlit.testing.v1 import AppTest

FACTOR_LAB_PAGE = (
    Path(__file__).parents[2]
    / "src"
    / "quant_platform"
    / "web"
    / "pages"
    / "9_factor_lab.py"
)


def test_evaluation_error_keeps_following_tabs_rendered(
    tmp_path: Path, monkeypatch
) -> None:
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
