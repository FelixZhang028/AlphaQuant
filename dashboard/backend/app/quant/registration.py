"""谁可以注册：开放、凭邀请码、或者暂停注册。

- ``FELLOWQUANT_REGISTRATION=closed``：不开放注册（已有账户照常登录）；
- ``FELLOWQUANT_INVITE_CODES``：填了就必须凭邀请码注册。多个用逗号分开，``码:次数`` 限制每个码能用几次，
  例如 ``FRIENDS2026:20,TEAM-A``（TEAM-A 不限次数）；
- 都不填：开放注册。

邀请码不区分大小写；用过的次数记在数据库里，重启后仍然有效。
"""

from __future__ import annotations

import os

from fastapi import HTTPException


def invite_codes() -> dict[str, int | None]:
    """``{码（大写）: 最多次数或 None（不限）}``；写错的次数当作不限会更危险，所以当作 0。"""

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


def mode() -> str:
    """``closed``、``invite`` 或 ``open``。"""

    if os.getenv("FELLOWQUANT_REGISTRATION", "").strip().lower() == "closed":
        return "closed"
    return "invite" if invite_codes() else "open"


def claim(conn, code: str) -> str | None:
    """Check the invite code for a registration in ``conn``'s transaction and count one use.

    Returns the code used (None when registration is open); raises 403 when it may not be used."""

    current = mode()
    if current == "closed":
        raise HTTPException(status_code=403, detail="暂时不开放注册。")
    if current == "open":
        return None
    codes = invite_codes()
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
