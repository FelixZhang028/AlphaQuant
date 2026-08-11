"""Pure display helpers shared by backtest history pages."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd

from quant_platform.backtest.run_store import RunRecord
from quant_platform.web.run_labels import format_run_label

RUN_KIND_LABELS = {
    "single": "单次回测",
    "optimization": "参数优化",
    "walk_forward_oos": "样本外验证",
}


def localized_parameters(
    raw: Any,
    strategy_plugin: Any,
    metadata_by_name: Mapping[str, Any],
) -> str:
    """Translate persisted parameter keys without changing stored data."""

    try:
        values = json.loads(raw) if isinstance(raw, str) else dict(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return str(raw)
    metadata = metadata_by_name.get(str(strategy_plugin))
    labels = (
        {parameter.name: parameter.label for parameter in metadata.parameters}
        if metadata is not None
        else {}
    )
    return json.dumps(
        {labels.get(str(name), str(name)): value for name, value in values.items()},
        ensure_ascii=False,
    )


def comparison_display_frame(
    comparison: pd.DataFrame,
    metadata_by_name: Mapping[str, Any],
    strategy_names: Mapping[str, str],
) -> pd.DataFrame:
    """Select and localize the useful comparison columns."""

    important = [
        column
        for column in (
            "run_id",
            "strategy",
            "parameters",
            "start_date",
            "end_date",
            "cumulative_return",
            "annual_return",
            "max_drawdown",
            "sharpe",
            "sortino",
            "calmar",
            "validity_status",
            "metrics_reliable",
            "legacy_unverified",
            "total_transaction_cost",
            "orders",
            "risk_rejections",
            "risk_adjustments",
        )
        if column in comparison.columns
    ]
    result = comparison[important].copy()
    if "parameters" in result.columns:
        result["parameters"] = result.apply(
            lambda row: localized_parameters(
                row["parameters"], row.get("strategy"), metadata_by_name
            ),
            axis=1,
        )
    if "strategy" in result.columns:
        result["strategy"] = result["strategy"].map(
            lambda value: strategy_names.get(str(value), value)
        )
    return result


def run_catalog_frame(
    records: Sequence[RunRecord], strategy_names: Mapping[str, str]
) -> pd.DataFrame:
    """Build the searchable run-library table."""

    return pd.DataFrame(
        [
            {
                "run_id": record.run_id,
                "run_label": format_run_label(record, strategy_names),
                "strategy": strategy_names.get(
                    record.strategy_plugin, record.strategy_plugin or "旧版本策略"
                ),
                "strategy_id": record.strategy_id,
                "run_kind": record.run_kind,
                "status": record.status.value,
                "start_date": record.start_date,
                "end_date": record.end_date,
                "updated_at": record.updated_at,
                "parent_experiment_id": record.parent_experiment_id,
                "baseline_run_id": record.baseline_run_id,
                "error": record.error,
            }
            for record in records
        ]
    )
