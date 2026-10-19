"""注销账户时删除这个用户的全部数据，或者导出一份副本（个人信息保护法：用户可以要求删除、复制个人信息）。

数据库里的数据：用户表的其他表都设置了 ON DELETE CASCADE，删除用户这一行时一起删除。
文件里的数据：AI 研究员的研究经验和设置（``agent_lab/<用户>``），以及这个用户的回测运行文件。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..database import get_conn


def _run_directories(user_id: int) -> list[Path]:
    from .run_evidence import run_directory

    with get_conn() as conn:
        rows = conn.execute("SELECT result FROM backtests WHERE user_id = ?", (user_id,)).fetchall()
    directories = []
    for row in rows:
        try:
            result: dict[str, Any] = json.loads(row["result"]) if row["result"] else {}
        except ValueError:
            continue
        directory = run_directory(result)  # 只会是运行目录里的路径
        if directory is not None:
            directories.append(directory)
    return directories


def delete_account(user_id: int) -> None:
    from ..routes.agent_lab import _user_dir

    files = [*_run_directories(user_id), _user_dir(user_id)]
    with get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    for path in files:
        shutil.rmtree(path, ignore_errors=True)


# 导出时账户本身只给这几项；密码哈希、盐和令牌版本不属于“个人信息的副本”，也不应该离开服务器。
_ACCOUNT_FIELDS = ("name", "email", "created_at", "last_seen_at")


def _readable(value: Any) -> Any:
    """数据库里存成 JSON 文本的列（策略定义、回测结果、AI 解读……）还原成对象，导出的文件更好读。"""

    if isinstance(value, str) and value[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def export_account(user_id: int) -> dict[str, Any]:
    """这个用户的全部数据：账户信息、数据库里每张属于他的表、AI 研究员的研究经验。

    按表结构自动找出带 ``user_id`` 的表，以后加了新表也会一起导出。"""

    from ..routes.agent_lab import _prior_store

    with get_conn() as conn:
        account = conn.execute(f"SELECT {', '.join(_ACCOUNT_FIELDS)} FROM users WHERE id = ?", (user_id,)).fetchone()
        tables = {}
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            columns = [row["name"] for row in conn.execute(f'PRAGMA table_info("{name}")')]
            if name == "users" or "user_id" not in columns:
                continue
            rows = conn.execute(f'SELECT * FROM "{name}" WHERE user_id = ?', (user_id,)).fetchall()
            tables[name] = [{key: _readable(row[key]) for key in columns if key != "user_id"} for row in rows]
    experience = [entry.to_dict() for entry in _prior_store(user_id).list()]
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": dict(account) if account else None,
        "tables": tables,
        "research_experience": experience,
    }
