"""Human-readable provider-route summary for persisted data manifests."""

from __future__ import annotations

import json

import pandas as pd


def add_provider_route_summary(manifests: pd.DataFrame) -> pd.DataFrame:
    """Add ``provider_route``, ``fallback_used``, and related columns."""

    result = manifests.copy()

    def summarize(value: object) -> tuple[str, bool, str, bool | None]:
        try:
            parameters = json.loads(str(value))
        except (json.JSONDecodeError, TypeError, ValueError):
            return "", False, "", None
        attempts = parameters.get("provider_attempts", [])
        if not isinstance(attempts, list):
            attempts = []
        labels: list[str] = []
        failed = False
        succeeded = False
        for attempt in attempts:
            if not isinstance(attempt, dict):
                continue
            source = str(attempt.get("source", ""))
            status = str(attempt.get("status", ""))
            labels.append(f"{source}:{status}")
            failed = failed or status == "failed"
            succeeded = succeeded or status == "success"
        requested = parameters.get("requested_sources", parameters.get("configured_sources", []))
        requested_route = (
            " -> ".join(str(source) for source in requested) if isinstance(requested, list) else ""
        )
        fallback = parameters.get("fallback_enabled")
        fallback_enabled = fallback if isinstance(fallback, bool) else None
        return (
            " -> ".join(labels),
            failed and succeeded,
            requested_route,
            fallback_enabled,
        )

    if "parameters_json" not in result.columns:
        result["provider_route"] = ""
        result["fallback_used"] = False
        result["requested_route"] = ""
        result["fallback_enabled"] = pd.NA
        return result
    summaries = result["parameters_json"].map(summarize)
    result["provider_route"] = summaries.map(lambda item: item[0])
    result["fallback_used"] = summaries.map(lambda item: item[1])
    result["requested_route"] = summaries.map(lambda item: item[2])
    result["fallback_enabled"] = summaries.map(lambda item: item[3])
    return result
