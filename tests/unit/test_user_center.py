"""Profile privacy and account-center navigation coverage."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from quant_platform.web.auth import AuthStore


def test_profile_returns_only_requested_users_public_fields(tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    assert store.register("alice", "alice@example.com", "password123", "password123").ok
    assert store.register("bob", "bob@example.com", "password456", "password456").ok
    profile = store.get_profile("ALICE")
    assert profile is not None
    assert profile["email"] == "alice@example.com"
    assert set(profile) == {"id", "username", "email", "created_at"}
    assert store.get_profile("' OR 1=1 --") is None


def test_account_center_sections_and_logout(monkeypatch, tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.register("alice", "alice@example.com", "password123", "password123")
    monkeypatch.setattr("quant_platform.web.auth.AuthStore", lambda: store)
    entrypoint = Path(__file__).resolve().parents[2] / "src/quant_platform/web/app.py"
    app = AppTest.from_file(entrypoint, default_timeout=30)
    app.session_state["aq_authenticated_user"] = "alice"
    app.run().switch_page("pages/16_user_center.py").run()
    assert not app.exception
    assert app.title[0].value == "个人中心"
    assert "alice@example.com" in [field.value for field in app.text_input]
    for section in ("使用偏好", "我的研究", "账号安全"):
        app.get("button_group")[0].set_value([section]).run()
        assert not app.exception
    app.session_state["private_test_value"] = "unsaved research"
    # Streamlit 1.50's ButtonGroup test adapter expects a list even in single mode.
    app.get("button_group")[0].set_value(["账号安全"])
    app.button(key="account_center_logout").click().run()
    assert not app.exception
    assert app.session_state["aq_authenticated_user"] is None
    assert "private_test_value" not in app.session_state


@pytest.mark.parametrize(
    "origin,title",
    [
        ("pages/14_settings.py", "设置"),
        ("pages/0_strategy_hub.py", "策略工作室"),
    ],
)
def test_account_returns_to_origin_after_section_changes(origin, title, monkeypatch, tmp_path):
    store = AuthStore(tmp_path / "auth.sqlite3")
    store.register("alice", "alice@example.com", "password123", "password123")
    monkeypatch.setattr("quant_platform.web.auth.AuthStore", lambda: store)
    entrypoint = Path(__file__).resolve().parents[2] / "src/quant_platform/web/app.py"
    app = AppTest.from_file(entrypoint, default_timeout=30)
    app.session_state["aq_authenticated_user"] = "alice"
    app.run().switch_page(origin).run()
    # Streamlit 1.50's test adapter represents single-selection groups as lists.
    for group in app.get("button_group"):
        group.set_value([group.value] if isinstance(group.value, str) else group.value)
    app.switch_page("pages/16_user_center.py").run()
    app.get("button_group")[0].set_value(["我的研究"]).run()
    app.get("button_group")[0].set_value(["我的研究"])
    app.button(key="account_center_back").click().run()
    assert not app.exception
    assert app.title[0].value == title


def test_direct_account_entry_returns_home():
    entrypoint = Path(__file__).resolve().parents[2] / "src/quant_platform/web/app.py"
    app = AppTest.from_file(entrypoint, default_timeout=30)
    app.session_state["aq_authenticated_user"] = "test-user"
    app.switch_page("pages/16_user_center.py").run()
    app.get("button_group")[0].set_value(["个人资料"])
    app.button(key="account_center_back").click().run()
    assert not app.exception
    assert app.title[0].value == "首页"
