"""可信度审计页的渲染冒烟测试。"""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_audit_report_page_renders() -> None:
    page_path = (
        Path(__file__).resolve().parents[2]
        / "src/quant_platform/web/app_pages/audit_report.py"
    )
    app = AppTest.from_file(page_path, default_timeout=60)

    app.run()

    assert not app.exception
    assert [title.value for title in app.title] == ["可信度审计"]
