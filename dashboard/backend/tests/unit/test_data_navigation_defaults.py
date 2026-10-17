"""股票池页面和数据服务共用默认值，首次编辑不悄悄切换标的或过滤条件。"""

import json
import sqlite3

import pytest

from app.quant import runtime
from app.routes import workspace


@pytest.fixture
def universe_db(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE universe (
        user_id INTEGER PRIMARY KEY, symbols TEXT, exclude_st INTEGER,
        exclude_suspended INTEGER, minimum_listing_days INTEGER,
        minimum_history_days INTEGER, minimum_average_amount REAL, updated_at TEXT
    )""")
    monkeypatch.setattr(workspace, "get_conn", lambda: conn)
    monkeypatch.setattr(runtime, "get_conn", lambda: conn)
    monkeypatch.setattr(workspace, "security_names", lambda: {})
    monkeypatch.setattr(workspace, "_local_symbol_stats", lambda: {})
    yield conn
    conn.close()


def test_new_user_sees_same_default_pool_as_data_service(universe_db):
    overview_service = runtime.build_data_center_service({"id": 123})
    page = workspace.universe_get({"id": 123})
    defaults, filters = runtime.default_universe_settings()
    assert [runtime.to_canonical(symbol) for symbol in page["symbols"]] == defaults
    assert overview_service.configured_symbols == defaults
    assert page["filters"] == filters
    assert universe_db.execute("SELECT COUNT(*) FROM universe").fetchone()[0] == 0


def test_first_edit_starts_from_displayed_pool_and_keeps_default_filters(universe_db):
    current = workspace.universe_get({"id": 123})
    assert workspace._load_universe_symbols(123) == current["symbols"]
    workspace._save_universe(123, current["symbols"] + ["300750"])
    saved = workspace.universe_get({"id": 123})
    assert saved["symbols"] == current["symbols"] + ["300750"]
    assert saved["filters"] == current["filters"]


def test_saved_custom_pool_and_filters_are_not_replaced(universe_db):
    universe_db.execute("INSERT INTO universe VALUES (?,?,?,?,?,?,?,?)", (
        123, json.dumps(["000001"]), 0, 1, 30, 42, 1234, "2026-10-10"
    ))
    before = workspace.universe_get({"id": 123})
    assert before["symbols"] == ["000001"]
    assert runtime.build_data_center_service({"id": 123}).configured_symbols == ["000001.SZ"]
    workspace._save_universe(123, ["000001", "600519"])
    after = workspace.universe_get({"id": 123})
    assert after["symbols"] == ["000001", "600519"]
    assert after["filters"] == before["filters"]
