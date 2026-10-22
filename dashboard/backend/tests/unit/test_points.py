"""积分：免费次数用完以后扣积分、先扣快过期的、失败退回、兑换码、管理员发放、每人每天上限。"""
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.quant import platform_ai, points
from app.routes import admin, auth
from app.routes import points as points_routes


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    monkeypatch.setenv("FELLOWQUANT_POINTS_SIGNUP", "100")
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_BRIEFS", "1")
    monkeypatch.setenv("FELLOWQUANT_AI_DAILY_QUESTIONS", "0")
    app = FastAPI()
    for router in (auth.router, points_routes.router, admin.router):
        app.include_router(router)
    current = {"user": {"id": 1, "is_admin": False}}
    app.dependency_overrides[auth.get_current_user] = lambda: current["user"]
    with database.get_conn() as conn:
        for uid, admin_flag in ((1, 0), (2, 0), (9, 1)):
            conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at, is_admin) VALUES (?, 'u', ?, 'h', 's', 'now', ?)",
                         (uid, f"u{uid}@example.test", admin_flag))
    return TestClient(app), current


def use(user, kind="brief"):
    with platform_ai.quota_call(user, kind):
        pass


def balance(uid):
    with database.get_conn() as conn:
        return points.balance(conn, uid)


def test_free_uses_come_first_then_points_and_the_gift_is_given_once(site):
    client, _ = site
    user = {"id": 1, "is_admin": False}
    body = client.get("/api/v1/points").json()
    assert body["balance"] == 100 and body["lots"][0]["label"] == "注册赠送" and body["signup_points"] == 100
    assert client.get("/api/v1/points").json()["balance"] == 100          # 只送一次
    brief = next(p for p in body["prices"] if p["kind"] == "brief")
    assert brief == {"kind": "brief", "label": "AI 解读", "free_per_day": 1, "free_left": 1, "used_today": 0, "cost": 3}
    use(user)                                                               # 免费的
    assert balance(1) == 100
    use(user)                                                               # 扣 3 积分
    assert balance(1) == 97
    assert platform_ai.usage(user, "brief") == {"limit": 1, "used": 2, "remaining": 0, "cost": 3, "points": 97}
    ledger = client.get("/api/v1/points").json()["ledger"]
    assert [(row["delta"], row["label"], row["feature"]) for row in ledger] == [(-3, "使用", "AI 解读"), (100, "注册赠送", "")]


def test_a_failed_call_gives_the_points_back(site):
    user = {"id": 1, "is_admin": False}
    with pytest.raises(RuntimeError):
        with platform_ai.quota_call(user, "question"):                     # 没有免费次数：直接扣 1
            assert balance(1) == 99
            raise RuntimeError("模型没有回答")
    assert balance(1) == 100 and platform_ai.usage(user, "question")["used"] == 0
    with database.get_conn() as conn:
        assert conn.execute("SELECT COUNT(*) FROM point_ledger WHERE kind = 'spend'").fetchone()[0] == 0


def test_not_enough_points_explains_what_to_do(site, monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_POINTS_SIGNUP", "2")
    user = {"id": 1, "is_admin": False}
    use(user)
    with pytest.raises(platform_ai.QuotaExceeded, match="再用一次要 3 积分，你现在有 2 积分") as refused:
        use(user)
    assert "兑换码" in str(refused.value) and balance(1) == 2


def test_the_points_closest_to_expiring_are_used_first(site):
    with database.get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        points.ensure_signup(conn, 1)                                      # 30 天有效
        points.grant(conn, 1, 2, "admin", 3, "很快过期")
        points.grant(conn, 1, 5, "admin", 365, "一年")
        points.spend(conn, 1, 4, "question")
        rows = conn.execute("SELECT note, remaining FROM point_lots l JOIN point_ledger g ON g.user_id = l.user_id "
                            "AND g.kind = l.source AND g.delta = l.amount ORDER BY l.expires_at").fetchall()
    assert [(r["note"], r["remaining"]) for r in rows] == [("很快过期", 0), ("欢迎使用镜思 Prismind", 98), ("一年", 5)]


def test_expired_points_do_not_count(site):
    with database.get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        points.ensure_signup(conn, 1)
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        conn.execute("UPDATE point_lots SET expires_at = ?", (past,))
    assert balance(1) == 0
    with pytest.raises(platform_ai.QuotaExceeded):
        use({"id": 1, "is_admin": False}, "question")


def test_administrators_pay_nothing_and_have_no_points(site):
    admin_user = {"id": 9, "is_admin": True}
    for _ in range(3):
        use(admin_user)
    assert platform_ai.usage(admin_user, "brief")["points"] is None and balance(9) == 0


def test_each_person_has_a_daily_cap(site, monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_POINTS_DAILY_CAP", "2")
    user = {"id": 1, "is_admin": False}
    use(user)
    use(user)
    with pytest.raises(platform_ai.QuotaExceeded, match="每人每天的上限（2 次）"):
        use(user, "question")
    assert balance(1) == 97                                                # 被拒绝的不扣积分


def test_redeem_codes(site):
    client, current = site
    current["user"] = {"id": 9, "is_admin": True, "email": "u9@example.test"}
    made = client.post("/api/v1/admin/redeem-codes", json={"count": 2, "points": 50, "valid_days": 7, "max_uses": 1, "note": "测试"})
    assert made.status_code == 201 and len(made.json()["created"]) == 2
    first, second = made.json()["created"]
    assert first.startswith("PM-") and len(first) == 17
    client.post(f"/api/v1/admin/redeem-codes/{second}/active", json={"active": False})

    current["user"] = {"id": 1, "is_admin": False}
    assert points.normalise_code(first.replace("-", " ").lower()) == first
    got = client.post("/api/v1/points/redeem", json={"code": f" {first.lower()} "})
    assert got.status_code == 200 and got.json()["points"] == 50 and got.json()["balance"] == 150
    assert client.post("/api/v1/points/redeem", json={"code": first}).status_code == 409     # 自己用过
    assert client.post("/api/v1/points/redeem", json={"code": second}).status_code == 404    # 停用了
    assert client.post("/api/v1/points/redeem", json={"code": "坏的"}).status_code == 400
    current["user"] = {"id": 2, "is_admin": False}
    assert client.post("/api/v1/points/redeem", json={"code": first}).status_code == 410     # 别人用完了

    current["user"] = {"id": 9, "is_admin": True, "email": "u9@example.test"}
    codes = {c["code"]: c for c in client.get("/api/v1/admin/points").json()["codes"]}
    assert codes[first]["used"] == 1 and codes[second]["active"] is False


def test_an_expired_code_cannot_be_redeemed(site):
    code = points.create_codes(1, 10, 30, None, 1, "")[0]
    with database.get_conn() as conn:
        conn.execute("UPDATE redeem_codes SET expires_at = ?", ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),))
    client, _ = site
    assert client.post("/api/v1/points/redeem", json={"code": code}).status_code == 410


def test_the_administrator_adds_and_takes_points(site):
    client, current = site
    current["user"] = {"id": 9, "is_admin": True, "email": "u9@example.test"}
    added = client.post("/api/v1/admin/users/1/points", json={"amount": 20, "days": 10, "note": "补偿"})
    assert added.status_code == 200 and added.json()["points"] == 120     # 先补上注册赠送
    assert client.post("/api/v1/admin/users/1/points", json={"amount": -500, "note": "扣"}).status_code == 400
    assert client.post("/api/v1/admin/users/1/points", json={"amount": -30, "note": "误发"}).json()["points"] == 90
    assert client.post("/api/v1/admin/users/9/points", json={"amount": 5, "note": "x"}).status_code == 400
    assert client.post("/api/v1/admin/users/1/points", json={"amount": 0, "note": "x"}).status_code == 400
    users = {u["id"]: u for u in client.get("/api/v1/admin/users").json()}
    assert users[1]["points"] == 90 and users[9]["points"] is None
    overview = client.get("/api/v1/admin/points").json()
    assert overview["outstanding"] == 90 and overview["given"] == {"signup": 100, "admin": 20}
    audit = client.get("/api/v1/admin/audit?kind=points").json()["items"]
    assert len(audit) == 2 and "补偿" in audit[1]["summary"]


def test_new_accounts_get_the_gift_when_they_register(site):
    client, _ = site
    made = client.post("/api/v1/auth/register", json={"name": "新", "email": "new@example.test", "password": "correct horse 1"})
    assert made.status_code == 201
    uid = made.json()["id"]
    assert balance(uid) == 100
