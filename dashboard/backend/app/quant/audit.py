"""What administrators did: changed settings, disabled users, started data jobs, made backups.

One row per action with a sentence for people to read and the details as JSON. Keys and passwords
never appear here: a settings change records which settings changed, not their values.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ..database import get_conn

# 种类 -> 页面上的说法（列表可以按种类筛选）。
KINDS = {
    "settings": "系统设置",
    "user": "用户",
    "registration": "注册与邀请码",
    "data": "数据任务",
    "backup": "备份",
}
MAX_ROWS = 500


def record(admin: dict[str, Any] | None, action: str, summary: str, **detail: Any) -> None:
    admin = admin or {}
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO admin_audit (admin_id, admin_email, action, summary, detail, created_at) VALUES (?,?,?,?,?,?)",
            (admin.get("id"), str(admin.get("email") or ""), action, summary[:300],
             json.dumps(detail, ensure_ascii=False, default=str), datetime.now(timezone.utc).isoformat()),
        )


def listing(kind: str = "", limit: int = 100) -> list[dict[str, Any]]:
    """Newest first; ``kind`` is a prefix from :data:`KINDS` (empty for everything)."""

    limit = max(1, min(int(limit), MAX_ROWS))
    with get_conn() as conn:
        if kind in KINDS:
            rows = conn.execute("SELECT * FROM admin_audit WHERE action LIKE ? ORDER BY id DESC LIMIT ?", (f"{kind}.%", limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM admin_audit ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": row["id"], "admin_email": row["admin_email"], "action": row["action"],
             "kind": KINDS.get(row["action"].split(".")[0], "其他"), "summary": row["summary"],
             "detail": json.loads(row["detail"] or "{}"), "created_at": row["created_at"]} for row in rows]
