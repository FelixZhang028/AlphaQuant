"""每个文本 AI 功能可以单独设置模型；没设置就用默认的文本模型。接口地址和密钥共用。"""

import pytest

from app.quant import platform_ai, site_config


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in ("FELLOWQUANT_AI_API_KEY", "OPENROUTER_API_KEY", "FELLOWQUANT_AI_BASE_URL", "FELLOWQUANT_AI_MODEL",
                 *(variable for variable, _ in platform_ai.TEXT_MODELS.values())):
        monkeypatch.delenv(name, raising=False)


def test_each_feature_uses_its_own_model_or_the_default(monkeypatch):
    assert platform_ai.platform_model(kind="chat") is None                       # 没有密钥：哪个功能都没有模型
    monkeypatch.setenv("FELLOWQUANT_AI_API_KEY", "k")
    monkeypatch.setenv("FELLOWQUANT_AI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL_CHAT", "deepseek-v4-flash")
    chat, brief, default = (platform_ai.platform_model(kind=kind) for kind in ("chat", "brief", None))
    assert chat.model == "deepseek-v4-flash" and brief.model == "deepseek-v4-pro" and default.model == "deepseek-v4-pro"
    assert chat.base_url == brief.base_url == "https://api.deepseek.com" and chat.api_key == brief.api_key == "k"
    assert platform_ai.platform_model(kind="decision").model == "deepseek-v4-pro"   # 不是文本功能：用默认
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL_CHAT", "  ")                        # 只有空格算没设置
    assert platform_ai.platform_model(kind="chat").model == "deepseek-v4-pro"


def test_the_admin_test_button_can_pass_unsaved_values():
    config = {"OPENROUTER_API_KEY": "k", "FELLOWQUANT_AI_MODEL_SCREEN": "deepseek/deepseek-v4-pro"}
    assert platform_ai.platform_model(config, kind="screen").model == "deepseek/deepseek-v4-pro"
    assert platform_ai.platform_model(config, kind="question").model == platform_ai.DEFAULT_MODEL


def test_the_settings_page_lists_one_model_per_text_feature():
    labels = [setting.label for setting in site_config.SETTINGS if setting.group == "ai"]
    for word in ("AI 解读", "选股解读", "追问", "AI 问答", "一句话生成规则"):
        assert f"{word}用的模型" in labels
    names = [setting.name for setting in site_config.SETTINGS]
    assert names.index("FELLOWQUANT_AI_MODEL_BRIEF") > names.index("FELLOWQUANT_AI_MODEL")
    brief = site_config.BY_NAME["FELLOWQUANT_AI_MODEL_BRIEF"]
    assert brief.kind == "text" and "deepseek-v4-flash" in brief.help and brief.default == "同文本模型名称"


def test_the_pages_show_the_model_each_feature_uses(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.routes import agent_lab, workspace
    from app.routes.auth import get_current_user

    monkeypatch.setenv("FELLOWQUANT_AI_API_KEY", "k")
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL_QUESTION", "deepseek-v4-flash")
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL_STRATEGY", "deepseek/deepseek-v4-flash")
    monkeypatch.setattr(platform_ai, "usage", lambda user, kind: {"limit": 3, "used": 0, "remaining": 3})
    monkeypatch.setattr(agent_lab, "_prior_store", lambda uid: type("Store", (), {"list": lambda self: []})())

    class Repository:
        def daily_bar_bounds(self):
            return None

    monkeypatch.setattr(agent_lab, "market_repository", lambda: Repository())
    app = FastAPI()
    app.include_router(agent_lab.router)
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "is_admin": False}
    client = TestClient(app)
    status = client.get("/api/v1/agent-lab/status").json()["ai"]
    assert status["model"] == "deepseek-v4-pro"
    assert status["models"] == {"brief": "deepseek-v4-pro", "question": "deepseek-v4-flash", "chat": "deepseek-v4-pro"}
    assert client.get("/api/v1/nl/status").json()["ai"]["model"] == "deepseek-v4-flash"     # OpenRouter 写法只显示后半段
