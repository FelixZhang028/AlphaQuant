"""专家先验知识：把用户自己的见解与网络观点作为 AI 分析的先验输入。

借鉴 PA_Agent 的「经验库 + 提示词工程库」思路：先验知识以结构化条目保存，
分析时聚合为一段文本注入到各个方向的 Agent 提示词中，让 AI 不再只凭行情数据
做机械化分析。条目只保存在本地 ``runtime/prior_knowledge.json``（已 gitignore）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

DEFAULT_PRIOR_PATH = Path("runtime/prior_knowledge.json")


@dataclass(frozen=True)
class PriorKnowledgeEntry:
    """一条先验知识。"""

    id: str
    content: str
    source: str
    created_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "content": self.content,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_mapping(cls, value: Any) -> PriorKnowledgeEntry:
        if not isinstance(value, dict):
            raise ValueError("先验知识条目格式无效")
        return cls(
            id=str(value.get("id", "")),
            content=str(value.get("content", "")),
            source=str(value.get("source", "")),
            created_at=datetime.fromisoformat(str(value.get("created_at"))),
        )


class PriorKnowledgeStore:
    """本地先验知识库：增 / 列 / 删 / 聚合渲染。"""

    def __init__(self, path: str | Path = DEFAULT_PRIOR_PATH) -> None:
        self.path = Path(path)

    def _read(self) -> list[dict[str, str]]:
        if not self.path.is_file():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _write(self, entries: list[PriorKnowledgeEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = [entry.to_dict() for entry in entries]
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def list(self) -> tuple[PriorKnowledgeEntry, ...]:
        entries: list[PriorKnowledgeEntry] = []
        for raw in self._read():
            try:
                entries.append(PriorKnowledgeEntry.from_mapping(raw))
            except (ValueError, KeyError):
                continue
        return tuple(sorted(entries, key=lambda item: item.created_at, reverse=True))

    def add(self, content: str, source: str = "我的观点") -> PriorKnowledgeEntry:
        content = re.sub(r"\s+", " ", content).strip()
        if not content:
            raise ValueError("先验知识内容不能为空")
        entry = PriorKnowledgeEntry(
            id=uuid4().hex[:8],
            content=content,
            source=source.strip() or "我的观点",
            created_at=datetime.now(UTC),
        )
        self._write([*self.list(), entry])
        return entry

    def delete(self, entry_id: str) -> None:
        self._write([entry for entry in self.list() if entry.id != entry_id])

    def render(self) -> str:
        """把全部先验知识聚合为一段可注入提示词的文本；空库返回空串。"""
        entries = self.list()
        if not entries:
            return ""
        lines = []
        for index, entry in enumerate(entries, start=1):
            lines.append(f"{index}. 【来源：{entry.source}】{entry.content}")
        return "\n".join(lines)
