"""积分：每天的免费次数用完以后，用积分继续使用 AI 功能。

规则：
- 每种 AI 功能每天有免费次数（``platform_ai.LIMITS``），先用免费次数，用完了每次扣一定的积分。
- 积分按“批”记：注册赠送、每日打卡、管理员发放、兑换码……每一批有自己的有效期。扣的时候先扣快过期的。
- 每日打卡：每个账户每天（北京时间）打一次卡。连续打卡送得越来越多（5、7、9……最多 15），断了从头开始；
  累计真正打卡 7 天送一张补签卡（不过期），补最近漏掉的一天，只接上连续天数、不送那天的积分。
- 调用失败（模型没有回答）时退回扣掉的积分，明细里也不留这一笔。
- 每个人每天最多用多少次（免费的加积分的），防止一个账户一直调用；管理员不扣积分、不受限制。
- 积分不能提现、不能转给别人。

表：``point_lots``（每一批积分和剩下多少）、``point_ledger``（每一次增加和扣除）、
``redeem_codes`` / ``redeem_uses``（兑换码和谁用过）、``point_checkins``（哪天打过卡，含补签）、
``point_makeup_cards``（补签卡）。时间都是 UTC 的 ISO 文本。
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from ..database import get_conn

# 每次使用要的积分（每天的免费次数用完以后）：种类 -> (环境变量, 默认)
COSTS = {
    "brief": ("FELLOWQUANT_POINTS_COST_BRIEF", 3),
    "question": ("FELLOWQUANT_POINTS_COST_QUESTION", 1),
    "strategy": ("FELLOWQUANT_POINTS_COST_STRATEGY", 2),
    "review": ("FELLOWQUANT_POINTS_COST_REVIEW", 2),
    "decision": ("FELLOWQUANT_POINTS_COST_DECISION", 2),
    "chat": ("FELLOWQUANT_POINTS_COST_CHAT", 2),
}
SIGNUP = ("FELLOWQUANT_POINTS_SIGNUP", 100)            # 新用户送多少积分
GIFT_DAYS = ("FELLOWQUANT_POINTS_GIFT_DAYS", 30)       # 赠送的积分多少天有效
DAILY_CAP = ("FELLOWQUANT_POINTS_DAILY_CAP", 200)      # 每人每天最多用多少次 AI（免费的加积分的），0 表示不限
CHECKIN = ("FELLOWQUANT_POINTS_CHECKIN", 5)             # 每日打卡：连续第 1 天送多少积分，0 表示关闭打卡
CHECKIN_STEP = ("FELLOWQUANT_POINTS_CHECKIN_STEP", 2)   # 连续打卡每多一天多送几分
CHECKIN_MAX = ("FELLOWQUANT_POINTS_CHECKIN_MAX", 15)    # 每天最多送几分（到了以后每天都送这么多）
CHECKIN_DAYS = ("FELLOWQUANT_POINTS_CHECKIN_DAYS", 30)  # 打卡的积分多少天有效
MAKEUP_EVERY = ("FELLOWQUANT_POINTS_MAKEUP_EVERY", 7)   # 累计真正打卡几天送一张补签卡（补签卡不过期），0 表示没有补签卡
MAKEUP_WINDOW = ("FELLOWQUANT_POINTS_MAKEUP_WINDOW", 7) # 补签卡最多补几天以内漏掉的日子

SOURCES = {"signup": "注册赠送", "checkin": "每日打卡", "admin": "管理员发放", "redeem": "兑换码", "purchase": "购买", "spend": "使用"}
CODE_PATTERN = re.compile(r"^[A-Z0-9-]{6,40}$")
CHINA = timezone(timedelta(hours=8))                    # 打卡按北京时间的日子算，和 AI 次数一样
_CODE_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class PointsShort(RuntimeError):
    """Not enough points for one more use (the free uses of the day are gone)."""


def _number(variable: tuple[str, int], minimum: int = 0) -> int:
    name, default = variable
    try:
        return max(minimum, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def cost(kind: str) -> int:
    return _number(COSTS[kind], 1) if kind in COSTS else 0


def daily_cap() -> int:
    return _number(DAILY_CAP)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat()


# --------------------------------------------------------------------------- #
# 余额和每一批
# --------------------------------------------------------------------------- #


def _live_lots(conn, user_id: int):
    """还有剩余、还没过期的每一批，先过期的在前。"""

    return conn.execute(
        "SELECT id, source, amount, remaining, expires_at, created_at FROM point_lots "
        "WHERE user_id = ? AND remaining > 0 AND expires_at > ? ORDER BY expires_at, id",
        (user_id, _iso(_now()))).fetchall()


def balance(conn, user_id: int) -> int:
    return sum(int(row["remaining"]) for row in _live_lots(conn, user_id))


def grant(conn, user_id: int, amount: int, source: str, days: int, note: str = "", detail: dict | None = None) -> int:
    """Add ``amount`` points valid for ``days`` days; returns the ledger id. Call inside a transaction."""

    if amount <= 0 or days <= 0:
        raise ValueError("积分和有效天数都要大于 0")
    now = _now()
    conn.execute("INSERT INTO point_lots (user_id, source, amount, remaining, expires_at, created_at) VALUES (?,?,?,?,?,?)",
                 (user_id, source, amount, amount, _iso(now + timedelta(days=days)), _iso(now)))
    cur = conn.execute("INSERT INTO point_ledger (user_id, delta, kind, feature, note, detail, created_at) VALUES (?,?,?,?,?,?,?)",
                       (user_id, amount, source, "", note, json.dumps(detail or {}, ensure_ascii=False), _iso(now)))
    return int(cur.lastrowid)


def _has_signup(conn, user_id: int) -> bool:
    return conn.execute("SELECT 1 FROM point_ledger WHERE user_id = ? AND kind = 'signup' LIMIT 1", (user_id,)).fetchone() is not None


def ensure_signup(conn, user_id: int) -> None:
    """Give the sign-up points once per account (also to accounts made before there were points).

    Outside a transaction it only takes the write lock when the gift is still missing, and checks again under the lock.
    """

    amount = _number(SIGNUP)
    if amount <= 0 or _has_signup(conn, user_id):
        return
    if not conn.in_transaction:
        conn.execute("BEGIN IMMEDIATE")
        if _has_signup(conn, user_id):
            return
    grant(conn, user_id, amount, "signup", _number(GIFT_DAYS, 1), "欢迎使用镜思 Prismind")


def _take(conn, user_id: int, amount: int) -> list[list[int]]:
    """Take ``amount`` from the live lots, soonest to expire first; ``[[lot id, taken], ...]``."""

    taken, need = [], amount
    for row in _live_lots(conn, user_id):
        if need <= 0:
            break
        part = min(need, int(row["remaining"]))
        conn.execute("UPDATE point_lots SET remaining = remaining - ? WHERE id = ?", (part, row["id"]))
        taken.append([int(row["id"]), part])
        need -= part
    return taken


def spend(conn, user_id: int, amount: int, feature: str) -> int:
    """Take ``amount`` points for one use of ``feature``; returns the ledger id. Raises PointsShort."""

    have = balance(conn, user_id)
    if have < amount:
        raise PointsShort(have)
    taken = _take(conn, user_id, amount)
    cur = conn.execute("INSERT INTO point_ledger (user_id, delta, kind, feature, note, detail, created_at) VALUES (?,?,?,?,?,?,?)",
                       (user_id, -amount, "spend", feature, "", json.dumps({"lots": taken}), _iso(_now())))
    return int(cur.lastrowid)


def refund(ledger_id: int) -> None:
    """The use failed: put the points back into the lots they came from and drop the ledger row."""

    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT detail FROM point_ledger WHERE id = ? AND kind = 'spend'", (ledger_id,)).fetchone()
        if row is None:
            return
        for lot_id, part in json.loads(row["detail"] or "{}").get("lots", []):
            conn.execute("UPDATE point_lots SET remaining = remaining + ? WHERE id = ?", (int(part), int(lot_id)))
        conn.execute("DELETE FROM point_ledger WHERE id = ?", (ledger_id,))


def adjust(conn, user_id: int, amount: int, note: str, days: int) -> int:
    """Administrator: add (``amount`` > 0, valid ``days``) or take away points (< 0, at most the balance)."""

    if amount > 0:
        return grant(conn, user_id, amount, "admin", days, note)
    have = balance(conn, user_id)
    if have < -amount:
        raise HTTPException(status_code=400, detail=f"这个用户只有 {have} 积分，不能扣 {-amount}")
    taken = _take(conn, user_id, -amount)
    cur = conn.execute("INSERT INTO point_ledger (user_id, delta, kind, feature, note, detail, created_at) VALUES (?,?,?,?,?,?,?)",
                       (user_id, amount, "admin", "", note, json.dumps({"lots": taken}), _iso(_now())))
    return int(cur.lastrowid)


# --------------------------------------------------------------------------- #
# 每日打卡
# --------------------------------------------------------------------------- #


def _china_today() -> date:
    return datetime.now(CHINA).date()


def reward(streak: int) -> int:
    """Points for the ``streak``-th day in a row: the start, then ``step`` more each day, at most the maximum."""

    start = _number(CHECKIN)
    if start <= 0 or streak <= 0:
        return 0
    return min(max(start, _number(CHECKIN_MAX)), start + _number(CHECKIN_STEP) * (streak - 1))


def _streak(seen: set[str], today: date) -> int:
    """Consecutive days checked in (made-up days count), ending today (or yesterday when today is not done yet)."""

    start = today if today.isoformat() in seen else today - timedelta(days=1)
    count = 0
    while (start - timedelta(days=count)).isoformat() in seen:
        count += 1
    return count


def _missed_day(seen: set[str], today: date) -> date | None:
    """The newest missed day a make-up card can fill. The whole gap must lie within the window (a check-in
    inside the window comes before it), so filling it can join the streak up again."""

    window = [today - timedelta(days=back) for back in range(1, _number(MAKEUP_WINDOW, 1) + 1)]
    for index, day in enumerate(window):
        if day.isoformat() not in seen:
            return day if any(older.isoformat() in seen for older in window[index + 1:]) else None
    return None


def _real_checkins(conn, user_id: int) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM point_checkins WHERE user_id = ? AND makeup = 0", (user_id,)).fetchone()[0])


def checkin_state(conn, user_id: int) -> dict[str, Any]:
    today = _china_today()
    seen = {r["day"] for r in conn.execute("SELECT day FROM point_checkins WHERE user_id = ? ORDER BY day DESC LIMIT 400",
                                           (user_id,)).fetchall()}
    done = today.isoformat() in seen
    streak = _streak(seen, today)
    real = _real_checkins(conn, user_id)
    every = _number(MAKEUP_EVERY)
    missed = _missed_day(seen, today) if every else None
    cards = int(conn.execute("SELECT COUNT(*) FROM point_makeup_cards WHERE user_id = ? AND used_day IS NULL",
                             (user_id,)).fetchone()[0]) if every else 0
    return {
        "enabled": _number(CHECKIN) > 0, "days": _number(CHECKIN_DAYS, 1),
        "ladder": [reward(n) for n in range(1, 8)],          # 连续第 1～7 天各送多少；第 7 天以后和第 7 天一样
        "done_today": done, "streak": streak, "total": real,
        # 今天打过：今天领了多少、明天能领多少；没打：今天打能领多少、明天接着打能领多少
        "today_points": reward(streak if done else streak + 1),
        "next_points": reward(streak + 1 if done else streak + 2),
        "cards": cards, "card_every": every, "card_in": (every - real % every) if every else None,
        "missed_day": missed.isoformat() if missed else None, "makeup_window": _number(MAKEUP_WINDOW, 1),
    }


def checkin(user: dict) -> dict[str, Any]:
    """Check in for today (China time) once. The points grow with the streak; every ``MAKEUP_EVERY``
    real check-ins (made-up days do not count) give a make-up card."""

    if _number(CHECKIN) <= 0:
        raise HTTPException(status_code=403, detail="每日打卡暂时关闭")
    if user.get("is_admin"):
        raise HTTPException(status_code=400, detail="管理员不用积分，不用打卡")
    today = _china_today().isoformat()
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT 1 FROM point_checkins WHERE user_id = ? AND day = ?", (user["id"], today)).fetchone():
            raise HTTPException(status_code=409, detail="今天已经打过卡了，明天再来")
        seen = {r["day"] for r in conn.execute("SELECT day FROM point_checkins WHERE user_id = ?", (user["id"],)).fetchall()}
        streak = _streak(seen | {today}, _china_today())
        amount = reward(streak)
        conn.execute("INSERT INTO point_checkins (user_id, day, points, makeup, created_at) VALUES (?,?,?,0,?)",
                     (user["id"], today, amount, _iso(_now())))
        ensure_signup(conn, user["id"])
        grant(conn, user["id"], amount, "checkin", _number(CHECKIN_DAYS, 1), f"连续第 {streak} 天")
        every = _number(MAKEUP_EVERY)
        card = bool(every and _real_checkins(conn, user["id"]) % every == 0)
        if card:
            conn.execute("INSERT INTO point_makeup_cards (user_id, earned_at) VALUES (?,?)", (user["id"], _iso(_now())))
        state = checkin_state(conn, user["id"])
        have = balance(conn, user["id"])
    return {"points": amount, "streak": streak, "days": _number(CHECKIN_DAYS, 1), "card_earned": card, "balance": have, "checkin": state}


def makeup(user: dict) -> dict[str, Any]:
    """Use one make-up card on the newest missed day within the window. The streak joins up again;
    the made-up day gives no points."""

    if user.get("is_admin"):
        raise HTTPException(status_code=400, detail="管理员不用积分，不用补签")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        card = conn.execute("SELECT id FROM point_makeup_cards WHERE user_id = ? AND used_day IS NULL ORDER BY id LIMIT 1",
                            (user["id"],)).fetchone()
        if card is None:
            raise HTTPException(status_code=400, detail="没有补签卡；累计打卡满一定天数会送一张")
        seen = {r["day"] for r in conn.execute("SELECT day FROM point_checkins WHERE user_id = ?", (user["id"],)).fetchall()}
        day = _missed_day(seen, _china_today())
        if day is None:
            raise HTTPException(status_code=409, detail=f"最近 {_number(MAKEUP_WINDOW, 1)} 天没有需要补签的日子")
        conn.execute("INSERT INTO point_checkins (user_id, day, points, makeup, created_at) VALUES (?,?,0,1,?)",
                     (user["id"], day.isoformat(), _iso(_now())))
        conn.execute("UPDATE point_makeup_cards SET used_day = ?, used_at = ? WHERE id = ?", (day.isoformat(), _iso(_now()), card["id"]))
        state = checkin_state(conn, user["id"])
    return {"day": day.isoformat(), "checkin": state}


# --------------------------------------------------------------------------- #
# 兑换码
# --------------------------------------------------------------------------- #


def new_code() -> str:
    body = "".join(secrets.choice(_CODE_LETTERS) for _ in range(12))
    return f"PM-{body[:4]}-{body[4:8]}-{body[8:]}"


def create_codes(count: int, points: int, valid_days: int, max_uses: int, expires_days: int | None, note: str) -> list[str]:
    """``count`` new codes, each worth ``points`` points (valid ``valid_days`` days after redeeming),
    usable by ``max_uses`` different accounts, and redeemable for ``expires_days`` days (None: no end)."""

    now = _now()
    ends = _iso(now + timedelta(days=expires_days)) if expires_days else None
    codes = []
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for _ in range(count):
            code = new_code()
            conn.execute("INSERT INTO redeem_codes (code, points, valid_days, max_uses, used, expires_at, active, note, created_at) "
                         "VALUES (?,?,?,?,0,?,1,?,?)", (code, points, valid_days, max_uses, ends, note.strip(), _iso(now)))
            codes.append(code)
    return codes


def set_code_active(code: str, active: bool) -> None:
    with get_conn() as conn:
        changed = conn.execute("UPDATE redeem_codes SET active = ? WHERE code = ?", (1 if active else 0, code.strip().upper())).rowcount
    if not changed:
        raise HTTPException(status_code=404, detail="没有这个兑换码")


def all_codes(limit: int = 300) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM redeem_codes ORDER BY created_at DESC, code LIMIT ?", (limit,)).fetchall()
    now = _iso(_now())
    return [{"code": r["code"], "points": r["points"], "valid_days": r["valid_days"], "max_uses": r["max_uses"], "used": r["used"],
             "expires_at": r["expires_at"], "active": bool(r["active"]), "expired": bool(r["expires_at"] and r["expires_at"] <= now),
             "note": r["note"], "created_at": r["created_at"]} for r in rows]


def normalise_code(code: str) -> str:
    """Upper case without spaces; a generated code typed with spaces or without dashes gets its dashes back."""

    key = re.sub(r"\s+", "", code or "").upper()
    compact = key.replace("-", "")
    if re.fullmatch(r"PM[A-Z0-9]{12}", compact):
        return f"PM-{compact[2:6]}-{compact[6:10]}-{compact[10:]}"
    return key


def redeem(user_id: int, code: str) -> dict[str, Any]:
    key = normalise_code(code)
    if not CODE_PATTERN.match(key):
        raise HTTPException(status_code=400, detail="兑换码格式不对")
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM redeem_codes WHERE code = ?", (key,)).fetchone()
        if row is None or not row["active"]:
            raise HTTPException(status_code=404, detail="没有这个兑换码，或者已经停用")
        if row["expires_at"] and row["expires_at"] <= _iso(_now()):
            raise HTTPException(status_code=410, detail="这个兑换码已经过期")
        if conn.execute("SELECT 1 FROM redeem_uses WHERE code = ? AND user_id = ?", (key, user_id)).fetchone():
            raise HTTPException(status_code=409, detail="你已经用过这个兑换码了")
        if row["max_uses"] is not None and int(row["used"]) >= int(row["max_uses"]):
            raise HTTPException(status_code=410, detail="这个兑换码已经被用完了")
        conn.execute("INSERT INTO redeem_uses (code, user_id, used_at) VALUES (?,?,?)", (key, user_id, _iso(_now())))
        conn.execute("UPDATE redeem_codes SET used = used + 1 WHERE code = ?", (key,))
        ensure_signup(conn, user_id)
        grant(conn, user_id, int(row["points"]), "redeem", int(row["valid_days"]), key, {"code": key})
        have = balance(conn, user_id)
    return {"points": int(row["points"]), "valid_days": int(row["valid_days"]), "balance": have}


# --------------------------------------------------------------------------- #
# 给页面看的
# --------------------------------------------------------------------------- #


def summary(user: dict, limit: int = 100) -> dict[str, Any]:
    """Balance, live lots (with when they expire), the newest ledger rows and the price of each feature."""

    from . import platform_ai

    with get_conn() as conn:
        ensure_signup(conn, user["id"])
        lots = _live_lots(conn, user["id"])
        checked = checkin_state(conn, user["id"])
        rows = conn.execute("SELECT id, delta, kind, feature, note, created_at FROM point_ledger WHERE user_id = ? "
                            "ORDER BY id DESC LIMIT ?", (user["id"], limit)).fetchall()
    labels = {kind: word for kind, (_v, _d, word) in platform_ai.LIMITS.items()}
    prices = []
    for kind, word in labels.items():
        today = platform_ai.usage(user, kind)
        prices.append({"kind": kind, "label": word, "free_per_day": platform_ai.daily_limit(kind),
                       "free_left": today["remaining"], "used_today": today["used"], "cost": cost(kind)})
    return {
        "balance": sum(int(r["remaining"]) for r in lots),
        "lots": [{"id": r["id"], "source": r["source"], "label": SOURCES.get(r["source"], r["source"]), "amount": int(r["amount"]),
                  "remaining": int(r["remaining"]), "expires_at": r["expires_at"], "created_at": r["created_at"]} for r in lots],
        "ledger": [{"id": r["id"], "delta": int(r["delta"]), "kind": r["kind"], "label": SOURCES.get(r["kind"], r["kind"]),
                    "feature": labels.get(r["feature"], ""), "note": r["note"], "created_at": r["created_at"]} for r in rows],
        "prices": prices, "daily_cap": daily_cap(), "unlimited": bool(user.get("is_admin")),
        "signup_points": _number(SIGNUP), "gift_days": _number(GIFT_DAYS, 1), "checkin": checked,
    }


def overview(days: int = 30) -> dict[str, Any]:
    """Administrator: points given and used over the last ``days`` days, and the newest rows of all users."""

    since = _iso(_now() - timedelta(days=days))
    with get_conn() as conn:
        given = conn.execute("SELECT kind, COALESCE(SUM(delta), 0) AS n FROM point_ledger WHERE delta > 0 AND created_at >= ? GROUP BY kind",
                             (since,)).fetchall()
        used = conn.execute("SELECT feature, COALESCE(SUM(-delta), 0) AS n, COUNT(*) AS c FROM point_ledger WHERE kind = 'spend' AND created_at >= ? "
                            "GROUP BY feature", (since,)).fetchall()
        live = conn.execute("SELECT COALESCE(SUM(remaining), 0) AS n FROM point_lots WHERE remaining > 0 AND expires_at > ?",
                            (_iso(_now()),)).fetchone()
        recent = conn.execute("SELECT l.id, l.user_id, u.email, l.delta, l.kind, l.feature, l.note, l.created_at FROM point_ledger l "
                              "LEFT JOIN users u ON u.id = l.user_id ORDER BY l.id DESC LIMIT 50").fetchall()
    return {
        "days": days, "outstanding": int(live["n"]),
        "given": {r["kind"]: int(r["n"]) for r in given},
        "used": {r["feature"]: {"points": int(r["n"]), "times": int(r["c"])} for r in used},
        "recent": [{"id": r["id"], "user_id": r["user_id"], "email": r["email"] or "（已删除）", "delta": int(r["delta"]),
                    "kind": r["kind"], "label": SOURCES.get(r["kind"], r["kind"]), "feature": r["feature"], "note": r["note"],
                    "created_at": r["created_at"]} for r in recent],
    }
