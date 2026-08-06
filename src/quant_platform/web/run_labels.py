"""Human-readable labels for persisted backtest runs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from quant_platform.backtest.run_store import RunRecord

_LOCAL_TIMEZONE = ZoneInfo("Asia/Shanghai")


def format_run_label(record: RunRecord, strategy_names: Mapping[str, str]) -> str:
    """Describe a run without replacing its stable full identifier."""

    strategy = strategy_names.get(
        record.strategy_plugin,
        record.strategy_plugin or "旧版本策略",
    )
    instance = record.strategy_id.strip()
    if instance and instance not in {record.strategy_plugin, strategy}:
        strategy = f"{strategy}（{instance}）"

    dates = (
        f"区间 {record.start_date}～{record.end_date}"
        if record.start_date and record.end_date
        else "区间未知"
    )
    created_at = _local_time(record.created_at)
    parts = [strategy, dates]
    if created_at:
        parts.append(f"运行 {created_at}")
    parts.append(record.run_id[:8])
    return "｜".join(parts)


def _local_time(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(_LOCAL_TIMEZONE).strftime("%Y-%m-%d %H:%M")
