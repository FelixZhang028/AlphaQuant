"""Fail-closed trust labels shared by every view of a persisted backtest."""
import json
from pathlib import Path
from typing import Any

from quant_platform.backtest.validity import load_persisted_validity, legacy_unverified_report
from .runtime import BACKEND_ROOT, RUNTIME_ROOT


def run_directory(result: dict[str, Any]) -> Path | None:
    raw = result.get("output_dir")
    if not raw:
        return None
    path = Path(str(raw))
    path = (path if path.is_absolute() else BACKEND_ROOT / path).resolve()
    return path if path.is_relative_to((RUNTIME_ROOT / "runs").resolve()) else None


def run_evidence(result: dict[str, Any]) -> dict[str, Any]:
    directory = run_directory(result)
    validity = load_persisted_validity(directory) if directory else legacy_unverified_report()
    verified = bool(validity) and not validity.get("legacy_unverified", False)
    raw_issues = validity.get("issues")
    if not isinstance(raw_issues, list) or any(not isinstance(i, dict) for i in raw_issues):
        verified = False
        issues = [{"code": "CORRUPT_EVIDENCE", "severity": "ERROR", "message": "审计证据格式损坏，无法验证。"}]
    else:
        issues = list(raw_issues)
    status = str(validity.get("status") or "UNVERIFIED") if verified else "UNVERIFIED"
    if result.get("validity_status") == "INVALID":
        status = "INVALID"
    elif result.get("validity_status") == "WARNING" and status == "VALID":
        status = "WARNING"
    if verified and any(i.get("severity") == "ERROR" for i in issues):
        status = "INVALID"
    elif verified and any(i.get("severity") == "WARNING" for i in issues) and status == "VALID":
        status = "WARNING"
    reliable = (
        verified and status in {"VALID", "WARNING"}
        and validity.get("metrics_reliable") is True
        and result.get("metrics_reliable") is not False
        and not any(i.get("severity") == "ERROR" for i in issues)
    )
    return {
        "validity_status": status,
        "metrics_reliable": reliable,
        "legacy_unverified": not verified,
        "validity_issues": issues,
        "audit_version": validity.get("audit_version", 0),
    }


def with_run_evidence(result: dict[str, Any]) -> dict[str, Any]:
    directory = run_directory(result)
    kind = result.get("run_kind")
    if kind is None and directory:
        try:
            lifecycle = json.loads((directory / "run.json").read_text(encoding="utf-8"))
            kind = lifecycle.get("run_kind") if isinstance(lifecycle, dict) else None
        except (OSError, ValueError):
            pass
    return {**result, "run_kind": kind or "unknown", **run_evidence(result)}
