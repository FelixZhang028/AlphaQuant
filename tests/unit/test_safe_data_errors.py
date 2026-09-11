"""Failure messages never expose credentials in UI, exports or diagnostics."""

import logging
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from quant_platform.core.diagnostics import public_data_error, redact, redact_text
from quant_platform.core.logging import RedactingFormatter
from quant_platform.data.versioning import DataManifest


@pytest.mark.parametrize(
    "message",
    [
        "401 Client Error: https://example.test/api?token=private-test-secret&code=123",
        'password="private-test-secret"',
        "Authorization: Bearer private-test-secret",
        "https://user:private-test-secret@example.test/api",
    ],
)
def test_secrets_are_removed(message):
    assert "private-test-secret" not in redact_text(message)
    assert "private-test-secret" not in public_data_error(message)


def test_manifest_nested_metadata_and_traceback_are_redacted():
    manifest = DataManifest.start(
        "benchmark_bars",
        "xtick",
        {
            "token": "private-test-secret",
            "nested": {"api_key": "private-test-secret"},
        },
    ).fail(ValueError("https://example.test?token=private-test-secret"))
    assert "private-test-secret" not in manifest.to_frame().to_json(date_format="iso")
    assert redact({"password": "private-test-secret"}) == {"password": "[REDACTED]"}
    try:
        raise ValueError("https://example.test?token=private-test-secret")
    except ValueError:
        import sys

        record = logging.LogRecord("test", logging.ERROR, "test", 1, "failed", (), sys.exc_info())
        assert "private-test-secret" not in RedactingFormatter().format(record)


def test_old_update_results_are_grouped_and_hidden_from_page(tmp_path, monkeypatch):
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/app.yaml").write_text(
        "app:\n  runtime_dir: runtime\ndata:\n  repository: runtime/market\n"
        "universe:\n  config: configs/universe.yaml\nbacktest:\n  benchmark: 000300.SH\n",
        encoding="utf-8",
    )
    (tmp_path / "configs/universe.yaml").write_text(
        "universe:\n  symbols: ['000001.SZ']\n", encoding="utf-8"
    )
    page = Path(__file__).parents[2] / "src/quant_platform/web/app_pages/1_data_management.py"
    monkeypatch.chdir(tmp_path)
    app = AppTest.from_file(str(page))
    app.session_state["last_data_update"] = [
        {
            "dataset": "benchmark_bars",
            "version_id": str(i),
            "status": "FAILED",
            "rows": 0,
            "message": "private-test-secret",
            "error": "HTTPError: 401 Client Error https://example.test?token=private-test-secret",
        }
        for i in range(9)
    ]
    app.run(timeout=20)
    assert not app.exception
    assert len(app.error) == 1
    assert "9 项更新失败" in app.error[0].value
    assert "认证未通过" in app.error[0].value
    for element in [*app.markdown, *app.caption, *app.error]:
        assert "private-test-secret" not in element.value
        assert "HTTPError" not in element.value
    for table in app.dataframe:
        frame = table.value
        assert isinstance(frame, pd.DataFrame)
        assert "private-test-secret" not in frame.to_csv(index=False)
