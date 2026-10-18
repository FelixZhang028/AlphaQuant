"""注销账户时删除这个用户的全部数据（个人信息保护法：用户可以要求删除个人信息）。

数据库里的数据：用户表的其他表都设置了 ON DELETE CASCADE，删除用户这一行时一起删除。
文件里的数据：AI 研究员的研究经验和设置（``agent_lab/<用户>``），以及这个用户的回测运行文件。
"""

from __future__ import annotations

import json
import shutil
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
