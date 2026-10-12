"""Per-stock trades of a persisted run, as drawn on the K-line."""
import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.quant.run_trades import symbol_trades, traded_symbols
from app.routes import workspace
from app.routes.auth import get_current_user


def _fill(symbol, day, side, quantity, price, reference, commission, stamp_tax, transfer_fee, slippage):
    return {"symbol": symbol, "trade_date": day, "side": side, "quantity": quantity, "price": price,
            "reference_price": reference, "commission": commission, "stamp_tax": stamp_tax,
            "transfer_fee": transfer_fee, "slippage_cost": slippage}


def _order(symbol, day, status, reason=None, quantity=100):
    return {"symbol": symbol, "execution_date": day, "side": "BUY", "quantity": quantity,
            "status": status, "reject_reason": reason}


@pytest.fixture
def run_dir(tmp_path):
    days = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]
    pd.DataFrame({"trade_date": days, "equity": 1.0}).to_parquet(tmp_path / "nav.parquet")
    pd.DataFrame([
        _fill("000001.SZ", "2026-01-05", "BUY", 100, 10.01, 10.0, 5.0, 0.0, 0.01, 1.0),
        _fill("000001.SZ", "2026-01-07", "SELL", 100, 10.5, 10.51, 5.0, 0.53, 0.01, 1.0),
        _fill("000001.SZ", "2026-01-09", "BUY", 200, 10.2, 10.19, 5.0, 0.0, 0.02, 2.0),
        _fill("600519.SH", "2026-01-06", "BUY", 100, 1500.0, float("nan"), 45.0, 0.0, 1.5, 75.0),
    ]).to_parquet(tmp_path / "fills.parquet")
    pd.DataFrame([
        _order("000001.SZ", "2026-01-05", "FILLED"),
        _order("000001.SZ", "2026-01-08", "REJECTED", "OPEN_AT_UPPER_LIMIT", quantity=300),
        _order("300750.SZ", "2026-01-08", "REJECTED", "SOMETHING_NEW"),
    ]).to_parquet(tmp_path / "orders.parquet")
    pd.DataFrame([
        {"symbol": "000001.SZ", "trade_date": "2026-01-05", "quantity": 100},
        {"symbol": "000001.SZ", "trade_date": "2026-01-06", "quantity": 100},
        {"symbol": "000001.SZ", "trade_date": "2026-01-09", "quantity": 200},
        {"symbol": "600519.SH", "trade_date": "2026-01-06", "quantity": 100},
    ]).to_parquet(tmp_path / "positions.parquet")
    return tmp_path


def test_traded_symbols_count_fills_and_unfilled_orders(run_dir):
    rows = traded_symbols(run_dir, {"000001.SZ": "平安银行"})
    assert rows[0] == {"symbol": "000001", "name": "平安银行", "buys": 2, "sells": 1, "rejected": 1}
    assert [row["symbol"] for row in rows] == ["000001", "600519", "300750"]
    assert rows[2] == {"symbol": "300750", "name": "名称待补充", "buys": 0, "sells": 0, "rejected": 1}


def test_symbol_trades_keep_raw_prices_reasons_and_break_holdings_on_flat_days(run_dir):
    result = symbol_trades(run_dir, "000001")
    assert [(fill["date"], fill["side"], fill["price"]) for fill in result["fills"]] == [
        ("2026-01-05", "BUY", 10.01), ("2026-01-07", "SELL", 10.5), ("2026-01-09", "BUY", 10.2)]
    assert result["fills"][1]["fees"] == 5.54 and result["fills"][1]["slippage_cost"] == 1.0
    assert result["rejected"] == [{"date": "2026-01-08", "side": "BUY", "quantity": 300,
                                   "reason": "OPEN_AT_UPPER_LIMIT", "reason_label": "开盘涨停，无法买入"}]
    assert result["holdings"] == [{"start_date": "2026-01-05", "end_date": "2026-01-06"},
                                  {"start_date": "2026-01-09", "end_date": "2026-01-09"}]


def test_unknown_reasons_missing_numbers_and_absent_files_stay_serializable(run_dir):
    assert symbol_trades(run_dir, "300750")["rejected"][0]["reason_label"] == "订单未成交"
    assert symbol_trades(run_dir, "600519.SH")["fills"][0]["reference_price"] is None
    (run_dir / "positions.parquet").unlink()
    assert symbol_trades(run_dir, "000001")["holdings"] == []
    assert symbol_trades(run_dir, "000002") == {"symbol": "000002", "fills": [], "rejected": [], "holdings": []}


def test_trade_routes_resolve_the_users_run_and_validate_symbols(run_dir, monkeypatch):
    app = FastAPI()
    app.include_router(workspace.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": 7}
    row = {"strategy": "动量", "from_date": "2026-01-05", "to_date": "2026-01-09"}
    monkeypatch.setattr(workspace, "_audit_run_row", lambda ref, user: (row, {"output_dir": "ignored"}))
    monkeypatch.setattr(workspace, "run_directory", lambda result: run_dir)
    monkeypatch.setattr(workspace, "_local_market_catalog", lambda: type("Catalog", (), {"names": {}})())
    with TestClient(app) as client:
        listing = client.get("/api/v1/runs/run-1/trades").json()
        assert listing["run_label"] == "动量｜2026-01-05~2026-01-09" and len(listing["symbols"]) == 3
        assert len(client.get("/api/v1/runs/run-1/trades/000001").json()["fills"]) == 3
        assert client.get("/api/v1/runs/run-1/trades/oops").status_code == 422
        (run_dir / "fills.parquet").unlink()
        assert client.get("/api/v1/runs/run-1/trades").status_code == 404
