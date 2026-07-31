"""Version manifests for reproducible local market-data updates."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

import pandas as pd

from quant_platform.data.interfaces import MarketDataRepository


class ManifestStatus(StrEnum):
    """Lifecycle state for one dataset update."""

    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DataManifest:
    """Auditable metadata for one dataset ingestion attempt."""

    version_id: str
    dataset: str
    source: str
    status: ManifestStatus
    started_at: datetime
    completed_at: datetime | None
    row_count: int
    symbol_count: int
    min_date: date | None
    max_date: date | None
    parameters: dict[str, Any]
    quality: dict[str, Any]
    error: str | None = None

    @classmethod
    def start(cls, dataset: str, source: str, parameters: dict[str, Any]) -> DataManifest:
        """Create a running manifest with a sortable unique identifier."""

        now = datetime.now(UTC)
        version_id = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
        return cls(
            version_id=version_id,
            dataset=dataset,
            source=source,
            status=ManifestStatus.RUNNING,
            started_at=now,
            completed_at=None,
            row_count=0,
            symbol_count=0,
            min_date=None,
            max_date=None,
            parameters=parameters,
            quality={},
        )

    def succeed(
        self,
        *,
        row_count: int,
        symbol_count: int = 0,
        min_date: date | None = None,
        max_date: date | None = None,
        quality: dict[str, Any] | None = None,
    ) -> DataManifest:
        """Return a successful immutable manifest."""

        return replace(
            self,
            status=ManifestStatus.SUCCESS,
            completed_at=datetime.now(UTC),
            row_count=row_count,
            symbol_count=symbol_count,
            min_date=min_date,
            max_date=max_date,
            quality=quality or {},
            error=None,
        )

    def fail(self, error: Exception) -> DataManifest:
        """Return a failed immutable manifest with a bounded error message."""

        message = f"{type(error).__name__}: {error}"
        return replace(
            self,
            status=ManifestStatus.FAILED,
            completed_at=datetime.now(UTC),
            error=message[:2000],
        )

    def to_frame(self) -> pd.DataFrame:
        """Serialize the manifest into a Parquet-friendly single row."""

        return pd.DataFrame(
            [
                {
                    "version_id": self.version_id,
                    "dataset": self.dataset,
                    "source": self.source,
                    "status": self.status.value,
                    "started_at": self.started_at,
                    "completed_at": self.completed_at,
                    "row_count": self.row_count,
                    "symbol_count": self.symbol_count,
                    "min_date": self.min_date,
                    "max_date": self.max_date,
                    "parameters_json": json.dumps(
                        self.parameters, ensure_ascii=False, default=str, sort_keys=True
                    ),
                    "quality_json": json.dumps(
                        self.quality, ensure_ascii=False, default=str, sort_keys=True
                    ),
                    "error": self.error,
                }
            ]
        )


def save_manifest(repository: MarketDataRepository, manifest: DataManifest) -> DataManifest:
    """Append one final manifest and return it for fluent orchestration."""

    repository.save_table("data_manifests", manifest.to_frame())
    return manifest


def latest_successful_manifest(
    repository: MarketDataRepository, dataset: str
) -> dict[str, Any] | None:
    """Return the newest successful manifest as a plain mapping."""

    frame = repository.read_table("data_manifests")
    if frame.empty:
        return None
    selected = frame[
        frame["dataset"].eq(dataset) & frame["status"].eq(ManifestStatus.SUCCESS.value)
    ]
    if selected.empty:
        return None
    selected = selected.sort_values("completed_at")
    return {str(key): value for key, value in selected.iloc[-1].to_dict().items()}
