"""Before going public: login and sign-up limits, invite codes, accounts, the AI budget and deployment settings."""
import importlib
import sqlite3
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database, security
from app.quant import backup, platform_ai, rate_limit
from app.routes import agent_lab, auth, backtests


@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    for name in ("FELLOWQUANT_INVITE_CODES", "FELLOWQUANT_REGISTRATION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(agent_lab, "_AGENT_ROOT", tmp_path / "agent_lab")
    app = FastAPI()
    app.include_router(auth.router)
    return TestClient(app)


def sign_up(client, email="a@example.test", password="correct horse 1", **extra):
    return client.post("/api/v1/auth/register", json={"name": "试用", "email": email, "password": password, **extra})


def log_in(client, email="a@example.test", password="correct horse 1"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# 频率限制
# --------------------------------------------------------------------------- #


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_RATE_LIMITS", "on")
    rate_limit.reset()


def test_wrong_passwords_pause_the_account_for_a_while(accounts, limits_on):
    assert sign_up(accounts).status_code == 201
    for _ in range(5):
        assert log_in(accounts, password="wrong password").status_code == 401
    paused = log_in(accounts)                                          # 密码对了也要等一会儿
    assert paused.status_code == 429 and "输错次数太多" in paused.json()["detail"] and "Retry-After" in paused.headers
    assert log_in(accounts, email="other@example.test").status_code == 401   # 别的账户不受影响


def test_a_right_password_clears_earlier_mistakes(accounts, limits_on):
    sign_up(accounts)
    for _ in range(4):
        log_in(accounts, password="wrong password")
    assert log_in(accounts).status_code == 200
    for _ in range(4):
        log_in(accounts, password="wrong password")
    assert log_in(accounts).status_code == 200


def test_one_address_cannot_sign_up_many_accounts(accounts, limits_on):
    for number in range(5):
        assert sign_up(accounts, email=f"user{number}@example.test").status_code == 201
    assert sign_up(accounts, email="user9@example.test").status_code == 429


def test_behind_a_proxy_the_real_address_is_used(accounts, limits_on, monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_CLIENT_IP_HEADER", "CF-Connecting-IP")
    for number in range(5):
        sign_up(accounts, email=f"u{number}@example.test")
    blocked = accounts.post("/api/v1/auth/register", json={"name": "n", "email": "x@example.test", "password": "p" * 10},
                            headers={"CF-Connecting-IP": "203.0.113.9"})
    assert blocked.status_code == 201                                   # 另一个真实地址


# --------------------------------------------------------------------------- #
# 谁可以注册
# --------------------------------------------------------------------------- #


def test_registration_can_require_an_invite_code_with_a_limited_number_of_uses(accounts, monkeypatch):
    assert accounts.get("/api/v1/auth/registration").json() == {"mode": "open"}
    monkeypatch.setenv("FELLOWQUANT_INVITE_CODES", "friends2026:2, TEAM")
    assert accounts.get("/api/v1/auth/registration").json() == {"mode": "invite"}
    assert sign_up(accounts).status_code == 403                                           # 没有邀请码
    assert "不正确" in sign_up(accounts, invite_code="guess").json()["detail"]
    assert sign_up(accounts, invite_code="FRIENDS2026").status_code == 201                  # 不区分大小写
    assert sign_up(accounts, invite_code="friends2026").status_code == 409                  # 邮箱已注册：不算用掉
    assert sign_up(accounts, email="b@example.test", invite_code="friends2026").status_code == 201
    assert "用完" in sign_up(accounts, email="c@example.test", invite_code="friends2026").json()["detail"]
    assert sign_up(accounts, email="c@example.test", invite_code="team").status_code == 201  # 不限次数


def test_registration_can_be_closed(accounts, monkeypatch):
    sign_up(accounts)
    monkeypatch.setenv("FELLOWQUANT_REGISTRATION", "closed")
    assert accounts.get("/api/v1/auth/registration").json() == {"mode": "closed"}
    assert sign_up(accounts, email="b@example.test").status_code == 403
    assert log_in(accounts).status_code == 200                                              # 已有账户照常登录


# --------------------------------------------------------------------------- #
# 密码与账户
# --------------------------------------------------------------------------- #


def test_old_password_hashes_still_work_and_are_upgraded_at_login(accounts):
    salt = security.gen_salt()
    legacy = security._pbkdf2("old style pw 1", salt, security.LEGACY_ITERATIONS)       # 以前存的格式
    with database.get_conn() as conn:
        conn.execute("INSERT INTO users (name, email, password_hash, salt, created_at) VALUES ('旧', 'old@example.test', ?, ?, 'now')",
                     (legacy, salt))
    assert log_in(accounts, "old@example.test", "old style pw 1").status_code == 200
    with database.get_conn() as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE email = 'old@example.test'").fetchone()[0]
    assert stored.startswith(f"pbkdf2_sha256${security.ITERATIONS}$") and not security.needs_rehash(stored)
    assert log_in(accounts, "old@example.test", "old style pw 1").status_code == 200
    assert log_in(accounts, "old@example.test", "wrong").status_code == 401


def test_overlong_passwords_are_refused_before_hashing(accounts):
    assert sign_up(accounts, password="x" * 129).status_code == 422
    assert log_in(accounts, password="x" * 10_000).status_code == 422


def test_changing_the_password_signs_out_other_devices(accounts):
    sign_up(accounts)
    first, second = log_in(accounts).json()["token"], log_in(accounts).json()["token"]
    wrong = accounts.post("/api/v1/auth/password", json={"old_password": "nope", "new_password": "new password 2"}, headers=bearer(first))
    assert wrong.status_code == 400
    changed = accounts.post("/api/v1/auth/password", json={"old_password": "correct horse 1", "new_password": "new password 2"},
                            headers=bearer(first))
    assert changed.status_code == 200
    assert accounts.get("/api/v1/auth/me", headers=bearer(second)).status_code == 401      # 另一台设备
    assert accounts.get("/api/v1/auth/me", headers=bearer(changed.json()["token"])).status_code == 200
    assert log_in(accounts, password="new password 2").status_code == 200


def test_logging_out_makes_the_token_useless(accounts):
    sign_up(accounts)
    token = log_in(accounts).json()["token"]
    assert accounts.post("/api/v1/auth/logout", headers=bearer(token)).status_code == 200
    assert accounts.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_deleting_an_account_removes_its_data_and_files(accounts, tmp_path, monkeypatch):
    from app.quant import run_evidence

    monkeypatch.setattr(run_evidence, "RUNTIME_ROOT", tmp_path / "runtime")
    sign_up(accounts)
    token = log_in(accounts).json()["token"]
    user_id = accounts.get("/api/v1/auth/me", headers=bearer(token)).json()["id"]
    run = tmp_path / "runtime" / "runs" / "r-1"
    run.mkdir(parents=True)
    (run / "summary.json").write_text("{}")
    elsewhere = tmp_path / "keep.txt"
    elsewhere.write_text("not the user's")
    with database.get_conn() as conn:
        conn.execute("INSERT INTO backtests (user_id, strategy, market, from_date, to_date, status, result, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (user_id, "s", "m", "2025-01-02", "2025-06-30", "完成", f'{{"output_dir": "{run.as_posix()}"}}', "now"))
        conn.execute("INSERT INTO backtests (user_id, strategy, market, from_date, to_date, status, result, created_at) VALUES (?,?,?,?,?,?,?,?)",
                     (user_id, "s", "m", "2025-01-02", "2025-06-30", "完成", f'{{"output_dir": "{elsewhere.as_posix()}"}}', "now"))
        conn.execute("INSERT INTO ai_usage (user_id, day, kind, count) VALUES (?, '2026-10-18', 'brief', 1)", (user_id,))
    prior = agent_lab._user_dir(user_id) / "prior_knowledge.json"
    prior.write_text("[]")
    assert accounts.post("/api/v1/auth/delete", json={"password": "wrong"}, headers=bearer(token)).status_code == 400
    assert accounts.post("/api/v1/auth/delete", json={"password": "correct horse 1"}, headers=bearer(token)).status_code == 200
    with database.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM backtests").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM ai_usage").fetchone()[0] == 0
    assert not run.exists() and not prior.exists()
    assert elsewhere.exists()                                         # 只删运行目录里的文件
    assert log_in(accounts).status_code == 401


def test_an_admin_cannot_delete_itself_here(accounts):
    sign_up(accounts)
    with database.get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = 1")
    token = log_in(accounts).json()["token"]
    assert accounts.post("/api/v1/auth/delete", json={"password": "correct horse 1"}, headers=bearer(token)).status_code == 403


# --------------------------------------------------------------------------- #
# 全站 AI 预算
# --------------------------------------------------------------------------- #


def test_the_whole_platform_has_a_daily_ai_budget(accounts, monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_TOTAL", "2")
    users = []
    for number in range(4):
        sign_up(accounts, email=f"u{number}@example.test")
        users.append({"id": number + 1, "is_admin": False})
    for user in users[:2]:
        with platform_ai.quota_call(user, "brief"):
            pass
    with pytest.raises(platform_ai.QuotaExceeded, match="平台今天的 AI 次数已经用完"):
        with platform_ai.quota_call(users[2], "brief"):
            pass
    with platform_ai.quota_call({"id": 4, "is_admin": True}, "brief"):   # 管理员不受限制
        pass
    # 失败的调用退回；注销的账户用过的次数仍然算在全站里。
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_TOTAL", "4")
    with pytest.raises(RuntimeError):
        with platform_ai.quota_call(users[2], "brief"):
            raise RuntimeError("模型没有回答")
    with platform_ai.quota_call(users[2], "brief"):
        pass
    with database.get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = 1")
    with pytest.raises(platform_ai.QuotaExceeded):
        with platform_ai.quota_call(users[3], "question"):
            pass


# --------------------------------------------------------------------------- #
# 只给管理员的策略
# --------------------------------------------------------------------------- #


def test_the_llm_multi_agent_strategy_is_for_admins_only(monkeypatch):
    from types import SimpleNamespace

    from app.routes.auth import get_current_user
    from quant_platform.strategies.discovery import StrategyCatalog

    catalog = StrategyCatalog()
    service = SimpleNamespace(available_strategies=catalog.metadata,
                              default_request=lambda: SimpleNamespace(strategy_plugin="a_share_momentum", strategy_parameters={}))
    monkeypatch.setattr(backtests, "build_backtest_service", lambda _: service)
    app = FastAPI()
    app.include_router(backtests.router)
    app.state.user = {"id": 1, "is_admin": False}
    app.dependency_overrides[get_current_user] = lambda: app.state.user
    client = TestClient(app)
    values = [item["value"] for item in client.get("/api/v1/backtests/catalog").json()["items"]]
    assert "llm_multi_agent" not in values and "a_share_momentum" in values
    with pytest.raises(Exception) as refused:
        backtests._resolve_plugin(service, "llm_multi_agent", app.state.user)
    assert getattr(refused.value, "status_code", None) == 403
    app.state.user = {"id": 1, "is_admin": True}
    assert "llm_multi_agent" in [item["value"] for item in client.get("/api/v1/backtests/catalog").json()["items"]]


# --------------------------------------------------------------------------- #
# 部署设置
# --------------------------------------------------------------------------- #


@pytest.fixture
def main_app(tmp_path, monkeypatch):
    """The real application, loaded with the given environment and an isolated account database."""

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FELLOWQUANT_DAILY_UPDATE", "off")
    monkeypatch.setenv("FELLOWQUANT_BACKUP", "off")
    import app.main as main

    def load(**env):
        for name in ("FELLOWQUANT_API_DOCS", "FELLOWQUANT_DEMO_MONITOR", "FELLOWQUANT_STATIC_DIR", "FELLOWQUANT_CORS_ORIGINS", "FELLOWQUANT_MAX_BODY_MB"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return TestClient(importlib.reload(main).app)

    yield load
    for name in ("FELLOWQUANT_API_DOCS", "FELLOWQUANT_DEMO_MONITOR", "FELLOWQUANT_STATIC_DIR", "FELLOWQUANT_CORS_ORIGINS", "FELLOWQUANT_MAX_BODY_MB"):
        monkeypatch.delenv(name, raising=False)
    importlib.reload(main)


def test_by_default_no_api_docs_no_demo_monitor_and_safe_headers(main_app):
    client = main_app()
    assert client.get("/docs").status_code == 404 and client.get("/openapi.json").status_code == 404
    assert client.get("/api/v1/stats/snapshot").status_code == 404
    health = client.get("/api/health")
    assert health.status_code == 200 and health.headers["X-Frame-Options"] == "DENY"
    assert health.headers["X-Content-Type-Options"] == "nosniff"
    big = client.post("/api/v1/auth/login", content=b"x" * (6 * 1024 * 1024), headers={"Content-Type": "application/json"})
    assert big.status_code == 413
    with_docs = main_app(FELLOWQUANT_API_DOCS="on", FELLOWQUANT_DEMO_MONITOR="on")
    assert with_docs.get("/docs").status_code == 200 and with_docs.get("/api/v1/stats/snapshot").status_code == 200


def test_cors_follows_the_configured_site(main_app):
    client = main_app(FELLOWQUANT_CORS_ORIGINS="https://fellowquant.example")
    allowed = client.options("/api/health", headers={"Origin": "https://fellowquant.example", "Access-Control-Request-Method": "GET"})
    assert allowed.headers.get("access-control-allow-origin") == "https://fellowquant.example"
    other = client.options("/api/health", headers={"Origin": "http://localhost:5273", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in other.headers


def test_the_backend_can_serve_the_built_site_on_one_address(main_app, tmp_path):
    site = tmp_path / "dist"
    site.mkdir()
    (site / "index.html").write_text("<html>首页</html>", encoding="utf-8")
    (site / "app.html").write_text("<html>功能台</html>", encoding="utf-8")
    client = main_app(FELLOWQUANT_STATIC_DIR=str(site))
    home = client.get("/")
    assert "首页" in home.text and "script-src 'self'" in home.headers["Content-Security-Policy"]
    assert "功能台" in client.get("/app.html").text
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/v1/auth/registration").status_code == 200        # 接口不受影响


# --------------------------------------------------------------------------- #
# 每日备份
# --------------------------------------------------------------------------- #


def test_a_daily_backup_is_complete_and_old_ones_are_pruned(tmp_path, monkeypatch):
    database_file = tmp_path / "app.db"
    conn = sqlite3.connect(database_file)
    conn.execute("CREATE TABLE users (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO users VALUES (1, '试用')")
    conn.commit()
    conn.close()
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "app-secret.key").write_text("secret")
    root = tmp_path / "backups"
    monkeypatch.setenv("FELLOWQUANT_BACKUP_KEEP", "2")
    first = backup.backup(date(2026, 10, 16), root=root, database=database_file, runtime=runtime)
    conn = sqlite3.connect(first / "app.db")
    try:
        assert conn.execute("SELECT name FROM users").fetchone()[0] == "试用"
    finally:
        conn.close()  # Windows 上不关闭就删不掉旧备份
    assert (first / "app-secret.key").read_text() == "secret"
    assert backup.backup(date(2026, 10, 16), root=root, database=database_file, runtime=runtime) is None   # 当天已经备份过
    backup.backup(date(2026, 10, 17), root=root, database=database_file, runtime=runtime)
    backup.backup(date(2026, 10, 18), root=root, database=database_file, runtime=runtime)
    assert sorted(p.name for p in root.iterdir()) == ["2026-10-17", "2026-10-18"]
