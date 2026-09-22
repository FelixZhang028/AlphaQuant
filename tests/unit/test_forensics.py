from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from quant_platform.forensics.checks import check_trades, load_evidence, verdict
from quant_platform.forensics.parsing import detect_columns, parse_trades, read_material

TEXT = "日期,代码,方向,数量（股）,成交价（未复权）\n2024-03-01,000001,买入,100,10\n"


def trades(text=TEXT):
    frame = read_material(text)
    parsed = parse_trades(frame, detect_columns(frame), "股")
    assert parsed.errors.empty
    return parsed.trades


def evidence():
    master = pd.DataFrame(
        [
            dict(
                symbol="000001.SZ",
                list_date=pd.Timestamp("1991-01-01"),
                delist_date=pd.NaT,
                source="test",
            )
        ]
    )
    bars = pd.DataFrame(
        [
            dict(
                symbol="000001.SZ",
                trade_date=pd.Timestamp("2024-03-01"),
                raw_low=9.0,
                raw_high=11.0,
                up_limit=11.0,
                down_limit=9.0,
                volume=10000.0,
                is_suspended=False,
                quality_status="OK",
                source="test",
            )
        ]
    )
    return master, bars


def test_clipboard_gbk_and_normalization():
    text = TEXT.replace(",", "\t").replace("000001,", "sz000001,")
    assert trades(text).iloc[0].symbol == "000001.SZ"
    assert trades(TEXT.encode("gb18030")).iloc[0].quantity == 100
    for symbol in ["sz000001", "000001.SZ", "1", "SZ.000001"]:
        assert trades(TEXT.replace("000001", symbol)).iloc[0].symbol == "000001.SZ"


def test_bad_rows_are_not_silently_dropped():
    frame = read_material(TEXT.replace("2024-03-01", "2024-02-30").replace(",100,10", ",NaN,-1"))
    parsed = parse_trades(frame, detect_columns(frame), "股")
    assert len(parsed.errors) == 3
    assert set(parsed.errors["表格行"]) == {2}
    with pytest.raises(ValueError):
        read_material("日期,日期\n1,2")


def test_valid_claim_and_missing_evidence():
    master, bars = evidence()
    assert verdict(check_trades(trades(), master, bars)) == "未发现异常"
    assert verdict(check_trades(trades(), master, pd.DataFrame())) == "证据不足"
    bars["quality_status"] = "UNKNOWN_STATUS"
    bars["raw_high"] = 1
    assert verdict(check_trades(trades(), master, bars)) == "证据不足"


def test_one_price_limit_is_only_suspicious():
    master, bars = evidence()
    bars[["raw_low", "raw_high", "up_limit"]] = 10.0
    assert verdict(check_trades(trades(), master, bars)) == "存在疑点"


@pytest.mark.parametrize("kind", ["unlisted", "suspended", "price", "volume"])
def test_specific_contradictions(kind):
    master, bars = evidence()
    if kind == "unlisted":
        master["list_date"] = pd.Timestamp("2025-01-01")
    elif kind == "suspended":
        bars["is_suspended"] = True
    elif kind == "price":
        bars["raw_high"] = 9.5
    else:
        bars["volume"] = 90.0
    findings = check_trades(trades(), master, bars)
    assert verdict(findings) == "发现明确矛盾"
    assert set(findings["表格行"]) == {2}
    assert findings["数据来源"].notna().all()


def test_adjusted_price_is_not_compared_and_volume_is_aggregated():
    master, bars = evidence()
    frame = trades(TEXT.replace(",100,10", ",60,1000") + "2024-03-01,000001,买入,60,1000\n")
    bars["volume"] = 100
    findings = check_trades(frame, master, bars, raw_prices=False)
    assert set(findings[findings["核查项"] == "成交价格"]["结论"]) == {"证据不足"}
    assert set(findings[findings["核查项"] == "成交占比"]["结论"]) == {"发现明确矛盾"}


def test_read_only_filtering(tmp_path):
    master, bars = evidence()
    master.to_parquet(tmp_path / "security_master.parquet")
    bars.to_parquet(tmp_path / "daily_bars.parquet")
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    loaded_master, loaded_bars = load_evidence(tmp_path, trades())
    assert len(loaded_master) == len(loaded_bars) == 1
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    absent = tmp_path / "absent"
    load_evidence(absent, trades())
    assert not absent.exists()


def test_hands_and_ambiguous_columns():
    frame = read_material(TEXT.replace("数量（股）", "数量（手）"))
    assert parse_trades(frame, detect_columns(frame), "手").trades.iloc[0].quantity == 10000
    frame["证券代码"] = "600519.SH"
    assert "symbol" not in detect_columns(frame)


def test_duplicate_bars_are_insufficient_evidence():
    master, bars = evidence()
    bars = pd.concat([bars, bars], ignore_index=True)
    assert verdict(check_trades(trades(), master, bars)) == "证据不足"


def test_external_page_without_backtest_and_stale_results(tmp_path, monkeypatch):
    from quant_platform.web import external_audit

    monkeypatch.setattr(
        external_audit, "load_app_config", lambda _: {"data": {"repository": str(tmp_path)}}
    )
    monkeypatch.setattr(external_audit, "load_evidence", lambda *args: evidence())
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/audit_report.py"
    app = AppTest.from_file(str(page), default_timeout=30)
    app.session_state["audit_subject"] = "外部材料"
    app.run()
    assert not app.exception
    app.text_area(key="external_trade_text").input(TEXT).run()
    assert not app.exception
    app.button(key="check_external").click().run()
    assert not app.exception
    assert any(item.value == "未发现异常" for item in app.subheader)
    app.text_area(key="external_trade_text").input(TEXT.replace(",100,10", ",100,1000")).run()
    assert not app.exception
    assert not app.subheader
    app.button(key="check_external").click().run()
    assert any(item.value == "发现明确矛盾" for item in app.subheader)
