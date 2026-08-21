"""Persist user strategy source files alongside small metadata sidecars."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quant_platform.core.exceptions import ConfigurationError

_CODE_FILENAME = "strategy.py"
_METADATA_FILENAME = "metadata.json"
_PLUGIN_NAME_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")


def _slugify(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", value).strip("-")
    return clean[:80] or "user_strategy"


@dataclass(frozen=True)
class UserStrategyRecord:
    """A saved user strategy: source file location and human metadata."""

    plugin_name: str
    display_name: str
    description: str
    source: str
    created_at: datetime
    updated_at: datetime
    directory: Path

    @property
    def code_path(self) -> Path:
        return self.directory / _CODE_FILENAME

    def read_code(self) -> str:
        return self.code_path.read_text(encoding="utf-8")

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "plugin_name": self.plugin_name,
            "display_name": self.display_name,
            "description": self.description,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_mapping(cls, value: Any, directory: Path) -> UserStrategyRecord:
        if not isinstance(value, dict) or int(value.get("version", 0)) != 1:
            raise ConfigurationError("不支持的自定义策略元数据文件")
        return cls(
            plugin_name=str(value.get("plugin_name", "")),
            display_name=str(value.get("display_name", "")),
            description=str(value.get("description", "")),
            source=str(value.get("source", "upload")),
            created_at=datetime.fromisoformat(str(value.get("created_at"))),
            updated_at=datetime.fromisoformat(str(value.get("updated_at"))),
            directory=directory,
        )


class UserStrategyStore:
    """CRUD for user strategies under ``runtime/user_strategies/<slug>/``."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save(
        self,
        code: str,
        *,
        plugin_name: str,
        display_name: str,
        description: str,
        source: str = "editor",
    ) -> UserStrategyRecord:
        if not _PLUGIN_NAME_RE.fullmatch(plugin_name):
            raise ConfigurationError(
                "策略标识只能包含字母、数字和下划线，且以字母开头"
            )
        directory = self.root / _slugify(plugin_name)
        now = datetime.now(UTC)
        existing = self._read_metadata(directory)
        created_at = existing.created_at if existing is not None else now
        record = UserStrategyRecord(
            plugin_name=plugin_name,
            display_name=display_name or plugin_name,
            description=description,
            source=source,
            created_at=created_at,
            updated_at=now,
            directory=directory,
        )
        directory.mkdir(parents=True, exist_ok=True)
        directory.joinpath(_CODE_FILENAME).write_text(code, encoding="utf-8")
        directory.joinpath(_METADATA_FILENAME).write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return record

    def list(self) -> tuple[UserStrategyRecord, ...]:
        if not self.root.exists():
            return ()
        records: list[UserStrategyRecord] = []
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir():
                continue
            record = self._read_metadata(directory)
            if record is not None and record.code_path.is_file():
                records.append(record)
        return tuple(sorted(records, key=lambda item: item.updated_at, reverse=True))

    def get(self, plugin_name: str) -> UserStrategyRecord | None:
        directory = self.root / _slugify(plugin_name)
        record = self._read_metadata(directory)
        if record is None or not record.code_path.is_file():
            return None
        return record

    def delete(self, plugin_name: str) -> None:
        directory = self.root / _slugify(plugin_name)
        if not directory.is_dir():
            return
        for path in directory.glob("*"):
            if path.is_file():
                path.unlink()
        directory.rmdir()

    @staticmethod
    def _read_metadata(directory: Path) -> UserStrategyRecord | None:
        path = directory / _METADATA_FILENAME
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return UserStrategyRecord.from_mapping(value, directory)
        except (ConfigurationError, json.JSONDecodeError, ValueError):
            return None
