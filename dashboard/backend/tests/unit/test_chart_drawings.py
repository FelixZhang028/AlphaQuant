"""Saved chart drawings: per user and stock, validated, replaced as a whole."""
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.routes import workspace
from app.routes.auth import get_current_user

URL = "/api/v1/data-center/market/{}/drawings"
SEGMENT = {"name": "segment", "points": [{"date": "2026-01-05", "price": 10.5}, {"date": "2026-02-06", "price": 12.0}]}
LEVEL = {"name": "horizontalStraightLine", "points": [{"date": "2026-01-05", "price": 11.25}]}


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    for key in ("FELLOWQUANT_ADMIN_EMAIL", "FELLOWQUANT_ADMIN_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    database.init_db()

    @contextmanager
    def connect():
        conn = database.get_conn()
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    monkeypatch.setattr(workspace, "get_conn", connect)
    with connect() as conn:
        for user in (101, 102):
            conn.execute("INSERT INTO users (id, name, email, password_hash, salt, created_at) VALUES (?,?,?,?,?,?)",
                         (user, f"u{user}", f"u{user}@example.test", "x", "x", "2026-01-01"))
    app = FastAPI()
    app.include_router(workspace.router)
    current = {"id": 101}
    app.dependency_overrides[get_current_user] = lambda: dict(current)
    return TestClient(app), current


def test_drawings_are_saved_per_user_and_stock_and_replaced_as_a_whole(api):
    client, current = api
    assert client.get(URL.format("000001")).json() == {"symbol": "000001", "drawings": [], "max_drawings": 50}
    saved = client.put(URL.format("000001.SZ"), json={"drawings": [SEGMENT, LEVEL]})
    assert saved.status_code == 200 and saved.json()["symbol"] == "000001"
    # 带不带交易所后缀都是同一只股票。
    assert client.get(URL.format("000001")).json()["drawings"] == [SEGMENT, LEVEL]
    assert client.get(URL.format("600519")).json()["drawings"] == []
    current["id"] = 102
    assert client.get(URL.format("000001")).json()["drawings"] == []
    current["id"] = 101
    assert client.put(URL.format("000001"), json={"drawings": [LEVEL]}).json()["drawings"] == [LEVEL]
    assert client.put(URL.format("000001"), json={"drawings": []}).json()["drawings"] == []
    assert client.get(URL.format("000001")).json()["drawings"] == []


@pytest.mark.parametrize("drawing", [
    {"name": "circle", "points": [{"date": "2026-01-05", "price": 10}]},
    {"name": "segment", "points": [{"date": "2026-01-05", "price": 10}]},
    {"name": "horizontalStraightLine", "points": [{"date": "2026-01-05", "price": 0}]},
    {"name": "horizontalStraightLine", "points": [{"date": "not-a-date", "price": 10}]},
])
def test_unknown_tools_incomplete_lines_and_bad_points_are_rejected(api, drawing):
    client, _ = api
    assert client.put(URL.format("000001"), json={"drawings": [drawing]}).status_code == 422
    assert client.get(URL.format("000001")).json()["drawings"] == []


def test_too_many_drawings_and_bad_symbols_are_rejected(api):
    client, _ = api
    assert client.put(URL.format("000001"), json={"drawings": [LEVEL] * 51}).status_code == 422
    assert client.put(URL.format("000001"), json={"drawings": [LEVEL] * 50}).status_code == 200
    assert client.get(URL.format("abc")).status_code == 422
    assert client.put(URL.format("0000011"), json={"drawings": []}).status_code == 422


def test_index_drawings_are_kept_apart_from_the_same_numbered_stock(api):
    client, _ = api
    saved = client.put(URL.format("000001.sh"), json={"drawings": [LEVEL]})
    assert saved.status_code == 200 and saved.json()["symbol"] == "000001.SH"
    assert client.get(URL.format("000001.SH")).json()["drawings"] == [LEVEL]
    # 平安银行（000001 / 000001.SZ）上没有上证指数的线。
    assert client.get(URL.format("000001")).json()["drawings"] == []
    assert client.get(URL.format("000001.SZ")).json()["drawings"] == []


def test_drawings_require_login():
    app = FastAPI()
    app.include_router(workspace.router)
    with TestClient(app) as client:
        assert client.get(URL.format("000001")).status_code == 401
        assert client.put(URL.format("000001"), json={"drawings": []}).status_code == 401
