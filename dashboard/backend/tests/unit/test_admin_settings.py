"""管理后台的系统设置：加密保存、只显示前后几位、要再输一次密码、立刻生效、可以改回用 .env；操作记录；AI 用量。"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.quant import audit, mailer, platform_ai, rate_limit, site_config
from app.routes import admin
from app.routes.auth import get_current_user
from app.security import gen_salt, hash_password
from trading_agents.llm.base import LLMResponse

PASSWORD = "admin-password-for-tests"
KEY = "sk-or-v1-0123456789abcdef"


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    salt = gen_salt()
    with database.get_conn() as conn:
        conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at, is_admin) VALUES (1, '管理员', 'admin@example.test', ?, ?, 'now', 1)",
                     (hash_password(PASSWORD, salt), salt))
        conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (2, '用户', 'u@example.test', 'x', 'y', 'now')")
    # 每个设置都由 monkeypatch 接管：测试里写进环境变量的值，结束后都会还原。
    # （先 setenv 再 delenv：原来没有的变量，delenv 不会记下要还原。）
    for name in site_config.BY_NAME:
        monkeypatch.setenv(name, "")
        monkeypatch.delenv(name)
    monkeypatch.setenv("FELLOWQUANT_AI_MODEL", "model-from-env")
    monkeypatch.setattr(site_config, "_ORIGINAL", {name: ("model-from-env" if name == "FELLOWQUANT_AI_MODEL" else None) for name in site_config.BY_NAME})
    rate_limit.reset()
    app = FastAPI()
    app.include_router(admin.router)
    current = {"user": {"id": 1, "name": "管理员", "email": "admin@example.test", "is_admin": True}}
    app.dependency_overrides[get_current_user] = lambda: current["user"]
    yield TestClient(app), current
    rate_limit.reset()


def item(body, name):
    return next(entry for group in body["groups"] for entry in group["items"] if entry["name"] == name)


def save(client, values=None, clear=None, password=PASSWORD):
    return client.put("/api/v1/admin/settings", json={"password": password, "values": values or {}, "clear": clear or []})


def test_a_saved_key_is_encrypted_masked_and_used_at_once(api):
    client, _ = api
    body = client.get("/api/v1/admin/settings").json()
    assert [group["label"] for group in body["groups"]] == ["AI 模型", "AI 次数", "数据更新", "邮件服务（找回密码）"]
    assert item(body, "FELLOWQUANT_AI_MODEL")["source"] == "env" and item(body, "OPENROUTER_API_KEY")["source"] == "default"
    assert platform_ai.platform_model() is None
    assert save(client, {"OPENROUTER_API_KEY": KEY, "FELLOWQUANT_AI_DAILY_CHATS": "50"}).status_code == 200
    # 立刻生效：不用重启
    assert platform_ai.platform_model().api_key == KEY and platform_ai.daily_limit("chat") == 50
    with database.get_conn() as conn:
        stored = conn.execute("SELECT value FROM site_settings WHERE key = 'config:OPENROUTER_API_KEY'").fetchone()["value"]
    assert stored.startswith("enc:") and KEY not in stored                          # 数据库里不是明文
    body = client.get("/api/v1/admin/settings").json()
    secret = item(body, "OPENROUTER_API_KEY")
    assert secret == {**secret, "value": "", "masked": "sk-o…cdef", "source": "admin", "configured": True}
    assert KEY not in str(body)                                                     # 完整的密钥不回传浏览器
    # 密钥留空表示不修改
    assert save(client, {"OPENROUTER_API_KEY": "", "FELLOWQUANT_AI_MODEL": "deepseek/other"}).json()["changed"] == ["FELLOWQUANT_AI_MODEL"]
    assert os.environ["OPENROUTER_API_KEY"] == KEY and platform_ai.platform_model().model == "deepseek/other"
    # 改回用 .env：.env 里有的还原，没有的就没有
    save(client, clear=["FELLOWQUANT_AI_MODEL", "OPENROUTER_API_KEY"])
    assert os.environ["FELLOWQUANT_AI_MODEL"] == "model-from-env" and "OPENROUTER_API_KEY" not in os.environ
    # 后端重启：保存的设置重新放进环境变量
    save(client, {"FELLOWQUANT_DAILY_UPDATE_TIME": "7:05"})
    os.environ.pop("FELLOWQUANT_DAILY_UPDATE_TIME")
    site_config.apply()
    assert os.environ["FELLOWQUANT_DAILY_UPDATE_TIME"] == "07:05"


def test_saving_needs_the_admin_password_and_valid_values(api, monkeypatch):
    client, current = api
    wrong = save(client, {"FELLOWQUANT_AI_DAILY_CHATS": "50"}, password="wrong")
    assert wrong.status_code == 403 and "FELLOWQUANT_AI_DAILY_CHATS" not in os.environ
    for values, reason in [({"FELLOWQUANT_AI_BASE_URL": "http://api.example.com/v1"}, "https://"),
                           ({"FELLOWQUANT_AI_BASE_URL": "ftp://x"}, "http"),
                           ({"FELLOWQUANT_AI_DAILY_CHATS": "-1"}, "之间"),
                           ({"FELLOWQUANT_DAILY_UPDATE_TIME": "25:00"}, "时:分"),
                           ({"FELLOWQUANT_DAILY_UPDATE": "maybe"}, "开或关"),
                           ({"SMTP_FROM": "not-an-email"}, "格式"),
                           ({"APP_SECRET": "x"}, "不认识")]:
        response = save(client, values)
        assert response.status_code == 422 and reason in response.json()["detail"], values
    assert save(client, {"FELLOWQUANT_AI_BASE_URL": "http://127.0.0.1:11434/v1/"}).status_code == 200   # 本机的服务可以用 http
    assert os.environ["FELLOWQUANT_AI_BASE_URL"] == "http://127.0.0.1:11434/v1"
    monkeypatch.setenv("FELLOWQUANT_RATE_LIMITS", "on")
    for _ in range(5):                                                               # 连续输错 5 次
        save(client, password="wrong")
    assert save(client, password=PASSWORD).status_code == 429                        # 先暂停，输对了也不行
    current["user"] = {"id": 2, "name": "用户", "email": "u@example.test", "is_admin": False}
    assert client.get("/api/v1/admin/settings").status_code == 403


def test_secrets_saved_with_another_app_secret_are_reported(api, monkeypatch):
    client, _ = api
    save(client, {"OPENROUTER_API_KEY": KEY})
    monkeypatch.setattr(site_config, "SECRET_KEY", "a-different-app-secret")
    assert item(client.get("/api/v1/admin/settings").json(), "OPENROUTER_API_KEY")["unreadable"] is True
    os.environ.pop("OPENROUTER_API_KEY")
    site_config.apply()
    assert "OPENROUTER_API_KEY" not in os.environ                                    # 解不开就不用


def test_settings_can_be_tried_before_saving(api, monkeypatch):
    client, _ = api
    seen = []

    class FakeText:
        def chat(self, messages, temperature=0.2, max_tokens=2048):
            return LLMResponse(text="收到", model="served-model")

    monkeypatch.setattr(platform_ai, "model_client", lambda model: seen.append(model) or FakeText())
    ok = client.post("/api/v1/admin/settings/test", json={"target": "text", "values": {"OPENROUTER_API_KEY": "unsaved-key-123456"}}).json()
    assert ok["ok"] is True and ok["model"] == "served-model" and seen[0].api_key == "unsaved-key-123456"
    assert "OPENROUTER_API_KEY" not in os.environ                                    # 测试不会保存
    assert client.post("/api/v1/admin/settings/test", json={"target": "decision"}).status_code == 422

    import requests

    class Broken:
        def chat(self, *args, **kwargs):
            response = MagicMock(status_code=401)
            raise requests.HTTPError(response=response)

    monkeypatch.setattr(platform_ai, "model_client", lambda model: Broken())
    failed = client.post("/api/v1/admin/settings/test", json={"target": "text", "values": {"OPENROUTER_API_KEY": "bad-key-123456"}}).json()
    assert failed == {"ok": False, "message": "平台的 AI 密钥无效，请联系管理员", "seconds": failed["seconds"]}

    with patch.object(mailer.smtplib, "SMTP") as smtp:
        sent = client.post("/api/v1/admin/settings/test", json={"target": "email", "values": {
            "SMTP_HOST": "smtp.example.test", "SMTP_FROM": "noreply@example.test", "SMTP_USERNAME": "noreply", "SMTP_PASSWORD": "pw"}}).json()
    assert sent == {"ok": True, "seconds": sent["seconds"], "to": "admin@example.test"}
    server = smtp.return_value.__enter__.return_value
    assert server.login.call_args.args == ("noreply", "pw") and server.send_message.call_args.args[0]["To"] == "admin@example.test"


def test_admin_actions_are_recorded_without_secrets(api):
    client, _ = api
    save(client, {"OPENROUTER_API_KEY": KEY, "FELLOWQUANT_AI_DAILY_TOTAL": "800"})
    client.post("/api/v1/admin/users/2/active", json={"active": False})
    client.put("/api/v1/admin/registration", json={"mode": "invite"})
    body = client.get("/api/v1/admin/audit").json()
    summaries = [row["summary"] for row in body["items"]]
    assert summaries[0] == "注册方式改为“凭邀请码注册”" and summaries[1] == "停用了账户 u@example.test"
    assert summaries[2].startswith("修改了系统设置：") and "OpenRouter 密钥" in summaries[2]
    assert KEY not in str(body) and body["items"][2]["admin_email"] == "admin@example.test"
    assert [row["kind"] for row in client.get("/api/v1/admin/audit", params={"kind": "user"}).json()["items"]] == ["用户"]


def test_ai_usage_by_day_kind_tokens_and_heaviest_users(api):
    client, _ = api
    day = platform_ai._today()
    with database.get_conn() as conn:
        conn.execute("INSERT INTO ai_usage (user_id, day, kind, count) VALUES (2, ?, 'chat', 4), (2, ?, 'brief', 1), (1, ?, 'chat', 2)", (day, day, day))

    class Inner:
        def chat(self, *args, **kwargs):
            return LLMResponse(text="好", prompt_tokens=120, completion_tokens=30)

    platform_ai.CountingClient(Inner()).chat([])
    body = client.get("/api/v1/admin/ai-usage", params={"days": 7}).json()
    today = body["days"][-1]
    assert len(body["days"]) == 7 and today["day"] == day
    assert today["kinds"]["chat"] == 6 and today["total"] == 7 and today["tokens"] == 150 and today["model_calls"] == 1
    assert [row["email"] for row in body["top_users"]] == ["u@example.test", "admin@example.test"]
    assert body["labels"]["chat"] == "AI 问答" and body["total"] == 7
    assert audit.listing() == []
