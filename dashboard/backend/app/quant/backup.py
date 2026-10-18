"""每天自动备份一次用户数据：账户数据库和几个只在本机的配置文件。

- 数据库用 SQLite 的在线备份接口复制，备份时网站照常使用，得到的是一份完整、一致的文件；
- 一起复制：登录令牌的签名密钥（丢了所有人都要重新登录）、数据源和知识库的设置；
- 放在 ``FELLOWQUANT_BACKUP_DIR``（默认 ``data/backups``，最好设成另一块硬盘或同步盘），
  每天一个文件夹，保留最近 ``FELLOWQUANT_BACKUP_KEEP`` 份（默认 14）；
- 行情数据不备份：体积大，而且可以从数据源重新下载。
- ``FELLOWQUANT_BACKUP=off`` 关闭。
"""

from __future__ import annotations

import logging
import os
import shutil
import sqlite3
import threading
from datetime import date
from pathlib import Path

from ..database import DB_PATH
from .runtime import BACKEND_ROOT, RUNTIME_ROOT

logger = logging.getLogger("uvicorn.error")
CHECK_SECONDS = 3600
EXTRA_FILES = ("app-secret.key", "data_source_settings.json", "weknora_settings.json")


def enabled() -> bool:
    return os.getenv("FELLOWQUANT_BACKUP", "on").strip().lower() not in ("0", "off", "false", "no")


def backup_root() -> Path:
    configured = os.getenv("FELLOWQUANT_BACKUP_DIR", "").strip()
    return Path(configured) if configured else BACKEND_ROOT / "data" / "backups"


def keep() -> int:
    try:
        return max(1, int(os.getenv("FELLOWQUANT_BACKUP_KEEP", "") or 14))
    except ValueError:
        return 14


def backup(today: date | None = None, *, root: Path | None = None, database: Path | None = None,
           runtime: Path | None = None) -> Path | None:
    """Back up today's data unless already done; returns the folder written (None if it existed)."""

    root = root or backup_root()
    folder = root / (today or date.today()).isoformat()
    if (folder / "app.db").exists():
        return None
    temporary = root / f".{folder.name}.partial"
    shutil.rmtree(temporary, ignore_errors=True)
    temporary.mkdir(parents=True)
    source = sqlite3.connect(str(database or DB_PATH))
    target = sqlite3.connect(str(temporary / "app.db"))
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    for name in EXTRA_FILES:
        path = (runtime or RUNTIME_ROOT) / name
        if path.exists():
            shutil.copy2(path, temporary / name)
    temporary.rename(folder)  # 复制完整以后才出现正式的文件夹
    folders = sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith("."))
    for old in folders[:-keep()]:
        shutil.rmtree(old, ignore_errors=True)
    return folder


class BackupScheduler:
    """Checks once an hour in a daemon thread and backs up once per day."""

    def __init__(self) -> None:
        self._stop = threading.Event()

    def tick(self) -> None:
        if not enabled():
            return
        try:
            folder = backup()
            if folder is not None:
                logger.info("已备份用户数据：%s", folder)
        except Exception:  # noqa: BLE001 - 备份失败不能影响网站
            logger.exception("每日备份失败")

    def _loop(self) -> None:
        self.tick()
        while not self._stop.wait(CHECK_SECONDS):
            self.tick()

    def start(self) -> None:
        threading.Thread(target=self._loop, name="daily-backup", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
