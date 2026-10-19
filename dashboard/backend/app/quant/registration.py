"""谁可以注册：开放、凭邀请码、或者暂停注册。

注册方式由管理员在管理后台选择（保存在数据库里）；没选过时按 .env：
- ``FELLOWQUANT_REGISTRATION=closed``：暂停注册，并且页面上不能改（已有账户照常登录）；
- ``FELLOWQUANT_INVITE_CODES``：填了就凭邀请码注册。多个用逗号分开，``码:次数`` 限制每个码能用几次，
  例如 ``FRIENDS2026:20,TEAM-A``（TEAM-A 不限次数）；
- 都不填：开放注册。

邀请码有两种来源：.env 里写的（只能在服务器上改）和管理员在管理后台生成的（可以停用）。
邀请码不区分大小写；用过的次数记在数据库里，重启后仍然有效。
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

from ..database import get_conn

MODES = ("open", "invite", "closed")
CODE_PATTERN = re.compile(r"^[A-Z0-9_-]{4,32}$")
_CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉容易看错的 0/O、1/I


def env_codes() -> dict[str, int | None]:
    """.env 里的邀请码 ``{码（大写）: 最多次数或 None（不限）}``；写错的次数当作不限会更危险，所以当作 0。"""

    codes: dict[str, int | None] = {}
    for item in os.getenv("FELLOWQUANT_INVITE_CODES", "").split(","):
        code, _, uses = item.strip().partition(":")
        if not code.strip():
            continue
        try:
            limit = int(uses) if uses.strip() else None
        except ValueError:
            limit = 0
        codes[code.strip().upper()] = limit
    return codes


def _saved_codes(conn) -> dict[str, int | None]:
    return {r["code"]: r["max_uses"] for r in conn.execute("SELECT code, max_uses FROM invite_codes WHERE active = 1")}


def invite_codes(conn=None) -> dict[str, int | None]:
    """所有能用的邀请码：管理后台生成的（未停用）加上 .env 里的。"""

    if conn is None:
        with get_conn() as conn:
            return {**_saved_codes(conn), **env_codes()}
    return {**_saved_codes(conn), **env_codes()}


def env_locked() -> bool:
    """.env 里写了暂停注册：页面上不能改。"""

    return os.getenv("FELLOWQUANT_REGISTRATION", "").strip().lower() == "closed"


def saved_mode(conn) -> str | None:
    row = conn.execute("SELECT value FROM site_settings WHERE key = 'registration'").fetchone()
    return row["value"] if row and row["value"] in MODES else None


def mode(conn=None) -> str:
    """``closed``、``invite`` 或 ``open``。"""

    if env_locked():
        return "closed"
    if conn is None:
        with get_conn() as conn:
            return mode(conn)
    chosen = saved_mode(conn)
    if chosen:
        return chosen
    return "invite" if env_codes() else "open"


def set_mode(value: str) -> None:
    if value not in MODES:
        raise HTTPException(status_code=400, detail="注册方式只能是开放、邀请码或暂停")
    if env_locked():
        raise HTTPException(status_code=409, detail="服务器的 .env 里设置了暂停注册，要先在服务器上去掉这一行。")
    with get_conn() as conn:
        conn.execute("INSERT INTO site_settings (key, value) VALUES ('registration', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (value,))


def new_code() -> str:
    return "FQ-" + "".join(secrets.choice(_CODE_LETTERS) for _ in range(8))


def create_code(code: str, max_uses: int | None, note: str) -> str:
    key = (code or "").strip().upper() or new_code()
    if not CODE_PATTERN.match(key):
        raise HTTPException(status_code=400, detail="邀请码只能用 4 到 32 位字母、数字、- 和 _")
    if key in env_codes():
        raise HTTPException(status_code=409, detail="这个邀请码已经写在 .env 里了")
    try:
        with get_conn() as conn:
            conn.execute("INSERT INTO invite_codes (code, max_uses, active, note, created_at) VALUES (?,?,1,?,?)",
                         (key, max_uses, note.strip(), datetime.now(timezone.utc).isoformat()))
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():
            raise HTTPException(status_code=409, detail="这个邀请码已经有了") from None
        raise
    return key


def set_code_active(code: str, active: bool) -> None:
    key = (code or "").strip().upper()
    if key in env_codes():
        raise HTTPException(status_code=409, detail="这个邀请码写在 .env 里，要在服务器上修改。")
    with get_conn() as conn:
        changed = conn.execute("UPDATE invite_codes SET active = ? WHERE code = ?", (1 if active else 0, key)).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="没有这个邀请码")


def all_codes() -> list[dict]:
    """管理后台列出的邀请码：.env 的在前，然后是页面生成的（最新的在前）。"""

    with get_conn() as conn:
        used = {r["code"]: int(r["used"]) for r in conn.execute("SELECT code, used FROM invite_uses")}
        saved = conn.execute("SELECT code, max_uses, active, note, created_at FROM invite_codes ORDER BY created_at DESC").fetchall()
    items = [{"code": code, "limit": limit, "used": used.get(code, 0), "active": True, "note": "", "source": "env",
              "created_at": None} for code, limit in env_codes().items()]
    items += [{"code": r["code"], "limit": r["max_uses"], "used": used.get(r["code"], 0), "active": bool(r["active"]),
               "note": r["note"], "source": "page", "created_at": r["created_at"]} for r in saved]
    return items


def claim(conn, code: str) -> str | None:
    """Check the invite code for a registration in ``conn``'s transaction and count one use.

    Returns the code used (None when registration is open); raises 403 when it may not be used."""

    current = mode(conn)
    if current == "closed":
        raise HTTPException(status_code=403, detail="暂时不开放注册。")
    if current == "open":
        return None
    codes = invite_codes(conn)
    key = (code or "").strip().upper()
    if key not in codes:
        raise HTTPException(status_code=403, detail="邀请码不正确。")
    limit = codes[key]
    row = conn.execute("SELECT used FROM invite_uses WHERE code = ?", (key,)).fetchone()
    used = int(row["used"]) if row else 0
    if limit is not None and used >= limit:
        raise HTTPException(status_code=403, detail="这个邀请码已经用完了。")
    conn.execute("INSERT INTO invite_uses (code, used) VALUES (?, 1) ON CONFLICT(code) DO UPDATE SET used = used + 1", (key,))
    return key
