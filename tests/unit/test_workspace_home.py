"""Routing coverage for the authenticated research home."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_authenticated_user_lands_on_workspace_home() -> None:
    app_path = Path(__file__).resolve().parents[2] / "src/quant_platform/web/app.py"
    app = AppTest.from_file(
        app_path,
        default_timeout=30,
    )
    app.session_state["aq_authenticated_user"] = "test-user"

    app.run()

    assert not app.exception
    assert [title.value for title in app.title] == ["首页"]
