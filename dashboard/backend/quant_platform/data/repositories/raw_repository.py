"""Immutable raw snapshot repository."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd


class RawDataRepository:
    """Write provider-native snapshots and request metadata without overwriting."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(
        self,
        provider: str,
        dataset: str,
        trade_date: date,
        frame: pd.DataFrame,
        request: dict[str, Any],
    ) -> Path:
        """Save one raw response under a timestamped snapshot directory."""

        captured = datetime.now(UTC)
        directory = (
            self.root
            / provider
            / dataset
            / f"trade_date={trade_date.isoformat()}"
            / captured.strftime("%Y%m%dT%H%M%S%fZ")
        )
        directory.mkdir(parents=True, exist_ok=False)
        data_path = directory / "data.parquet"
        frame.to_parquet(data_path, index=False)
        digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
        metadata = {
            "provider": provider,
            "dataset": dataset,
            "trade_date": trade_date.isoformat(),
            "captured_at": captured.isoformat(),
            "request": request,
            "rows": len(frame),
            "columns": list(frame.columns),
            "sha256": digest,
        }
        (directory / "metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return data_path
