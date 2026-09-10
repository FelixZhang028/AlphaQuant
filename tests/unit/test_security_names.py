from io import BytesIO
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from quant_platform.web.exports import dataframe_to_csv_bytes
from quant_platform.web.localization import localize_frame
from quant_platform.web.security_names import (
    load_security_names,
    security_label,
    with_security_names,
    xtick_security_names,
)


def _local_master(folder, name):
    (folder / "configs").mkdir(parents=True)
    (folder / "market").mkdir()
    (folder / "configs/app.yaml").write_text("data:\n  repository: market\n")
    pd.DataFrame({"symbol": ["000001.SZ"], "name": [name]}).to_parquet(
        folder / "market/security_master.parquet", index=False
    )


def test_names_preserve_codes_rows_existing_names_and_input():
    source = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "999999.SZ", "000001.SZ"],
            "name": [None, "历史名称", ""],
            "quantity": [1, 2, 3],
        },
        index=[7, 2, 9],
    )
    original = source.copy(deep=True)
    result = with_security_names(source, {"000001.SZ": "平安银行"})
    assert result.columns.tolist() == ["name", "symbol", "quantity"]
    assert result.name.tolist() == ["平安银行", "历史名称", "平安银行"]
    assert result.index.tolist() == [7, 2, 9]
    pd.testing.assert_frame_equal(source, original)
    pd.testing.assert_frame_equal(result, with_security_names(result, {}))


def test_unknown_security_and_index_are_not_mislabeled():
    result = with_security_names(pd.DataFrame({"symbol": ["000001.SH", "999999.SZ"]}))
    assert result.name.tolist() == ["上证指数", "未知名称"]
    assert security_label("999999.SZ", {}) == "未知名称（999999.SZ）"


def test_local_master_cache_updates_and_isolates_directories(tmp_path, monkeypatch):
    a, b = tmp_path / "a", tmp_path / "b"
    _local_master(a, "甲银行")
    _local_master(b, "乙银行")
    monkeypatch.chdir(a)
    assert load_security_names()["000001.SZ"] == "甲银行"
    pd.DataFrame({"symbol": ["000001.SZ"], "name": ["甲银行新名称"]}).to_parquet(
        a / "market/security_master.parquet", index=False
    )
    assert load_security_names()["000001.SZ"] == "甲银行新名称"
    monkeypatch.chdir(b)
    assert load_security_names()["000001.SZ"] == "乙银行"


def test_display_and_export_share_name_order(tmp_path, monkeypatch):
    _local_master(tmp_path, "平安银行")
    monkeypatch.chdir(tmp_path)
    raw = pd.DataFrame({"symbol": ["000001.SZ"], "raw_close": [10.0]})
    shown = localize_frame(raw)
    csv = pd.read_csv(BytesIO(dataframe_to_csv_bytes(raw)))
    assert shown.columns[:2].tolist() == ["股票名称", "股票代码"]
    assert csv.columns[:2].tolist() == ["name", "symbol"]
    assert csv.name.tolist() == shown["股票名称"].tolist() == ["平安银行"]


def test_missing_configuration_does_not_break_result_display(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert load_security_names() == {}
    assert localize_frame(pd.DataFrame({"symbol": ["999999.SZ"]}))["股票名称"].tolist() == [
        "未知名称"
    ]


def test_xtick_uses_asset_namespace_and_preserves_provider_name(tmp_path, monkeypatch):
    _local_master(tmp_path, "平安银行")
    monkeypatch.chdir(tmp_path)
    frame = pd.DataFrame({"code": ["000001"], "close": [10]})
    assert xtick_security_names(frame, "1").name.tolist() == ["平安银行"]
    assert xtick_security_names(frame, "2").name.tolist() == ["上证指数"]
    assert xtick_security_names(frame, "3").name.tolist() == ["未知名称"]
    assert xtick_security_names(frame, None).name.tolist() == ["未知名称"]
    frame["name"] = "接口提供名称"
    assert xtick_security_names(frame, "3").name.tolist() == ["接口提供名称"]


def test_data_page_shows_names_in_selector_coverage_and_quotes(tmp_path, monkeypatch):
    page = Path(__file__).resolve().parents[2] / "src/quant_platform/web/pages/1_data_management.py"
    _local_master(tmp_path, "平安银行")
    (tmp_path / "configs/app.yaml").write_text(
        "app:\n  runtime_dir: runtime\ndata:\n  repository: market\n"
        "universe:\n  config: configs/universe.yaml\nbacktest:\n  benchmark: 000300.SH\n"
    )
    (tmp_path / "configs/universe.yaml").write_text("universe:\n  symbols: [000001.SZ]\n")
    pd.DataFrame(
        {"symbol": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "raw_close": [10.0]}
    ).to_parquet(tmp_path / "market/daily_bars.parquet")
    pd.DataFrame({"cal_date": [pd.Timestamp("2024-01-02")], "is_open": [1]}).to_parquet(
        tmp_path / "market/trade_calendar.parquet"
    )
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(page), default_timeout=20).run()
    assert not app.exception
    selector = next(item for item in app.multiselect if item.key == "daily_bars_export_symbols")
    assert selector.options == ["平安银行（000001.SZ）"]
    assert selector.value == ["000001.SZ"]
    tables = [item.value for item in app.dataframe if "股票代码" in item.value.columns]
    assert len(tables) >= 3  # coverage, quotes and security master
    for table in tables:
        assert table.columns.get_loc("股票名称") + 1 == table.columns.get_loc("股票代码")
        assert table["股票名称"].iloc[0] == "平安银行"
