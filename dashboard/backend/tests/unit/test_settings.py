"""个人设置：研究默认值、今天的 AI 次数、导出我的数据。"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.quant import platform_ai
from app.routes import agent_lab, auth, settings


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    monkeypatch.setattr(agent_lab, "_AGENT_ROOT", tmp_path / "agent_lab")
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(agent_lab.router)
    test_client = TestClient(app)
    test_client.post("/api/v1/auth/register", json={"name": "试用", "email": "a@example.test", "password": "correct horse 1"})
    token = test_client.post("/api/v1/auth/login", json={"email": "a@example.test", "password": "correct horse 1"}).json()["token"]
    test_client.headers["Authorization"] = f"Bearer {token}"
    return test_client


def test_preferences_start_from_defaults_and_are_saved_per_account(client):
    first = client.get("/api/v1/settings/preferences").json()
    assert first["preferences"] == first["defaults"] and first["preferences"]["rebalance"] == "weekly"
    saved = {"initial_capital": 500000, "max_positions": 20, "rebalance": "monthly", "period_years": 3, "use_experience": False}
    assert client.put("/api/v1/settings/preferences", json=saved).status_code == 200
    assert client.get("/api/v1/settings/preferences").json()["preferences"] == saved
    assert client.put("/api/v1/settings/preferences", json={**saved, "max_positions": 80}).status_code == 422
    assert client.put("/api/v1/settings/preferences", json={**saved, "rebalance": "hourly"}).status_code == 422
    assert client.put("/api/v1/settings/preferences", json={**saved, "colour": "red"}).status_code == 422


def test_broken_saved_preferences_fall_back_to_defaults(client):
    with database.get_conn() as conn:
        conn.execute("INSERT INTO user_preferences (user_id, data, updated_at) VALUES (1, '{\"max_positions\": 999, \"x\": 1}', 'now')")
    data = client.get("/api/v1/settings/preferences").json()
    assert data["preferences"] == data["defaults"]


def test_usage_lists_every_kind_of_ai_call(client):
    with database.get_conn() as conn:
        conn.execute("INSERT INTO ai_usage (user_id, day, kind, count) VALUES (1, ?, 'brief', 2)", (platform_ai._today(),))
    usage = client.get("/api/v1/settings/usage").json()
    kinds = {item["kind"]: item for item in usage["items"]}
    assert set(kinds) == set(platform_ai.LIMITS) and usage["unlimited"] is False
    assert kinds["brief"]["used"] == 2 and kinds["brief"]["remaining"] == kinds["brief"]["limit"] - 2


def test_export_contains_my_data_but_no_password_and_nobody_elses(client):
    client.put("/api/v1/settings/preferences", json={"initial_capital": 300000, "max_positions": 5, "rebalance": "daily",
                                                     "period_years": 2, "use_experience": True})
    client.post("/api/v1/agent-lab/prior-knowledge", json={"content": "只看现金流为正的公司"})
    with database.get_conn() as conn:
        conn.execute("INSERT INTO users (name, email, password_hash, salt, created_at) VALUES ('别人', 'b@example.test', 'x', 'y', 'now')")
        conn.execute("INSERT INTO backtests (user_id, strategy, market, from_date, to_date, result, created_at) VALUES "
                     "(1, '动量', 'A股', '2025-01-01', '2025-06-30', '{\"total_return\": 3.2}', 'now'), "
                     "(2, '别人的', 'A股', '2025-01-01', '2025-06-30', '{}', 'now')")
    response = client.get("/api/v1/settings/export")
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    data = response.json()
    assert data["account"] == {"name": "试用", "email": "a@example.test", "created_at": data["account"]["created_at"],
                               "last_seen_at": data["account"]["last_seen_at"]}
    text = response.text
    assert "password" not in text and "salt" not in text and "token_version" not in text
    assert [b["strategy"] for b in data["tables"]["backtests"]] == ["动量"]
    assert data["tables"]["backtests"][0]["result"] == {"total_return": 3.2}          # JSON 文本还原成对象
    assert data["tables"]["user_preferences"][0]["data"]["initial_capital"] == 300000
    assert [e["content"] for e in data["research_experience"]] == ["只看现金流为正的公司"]
