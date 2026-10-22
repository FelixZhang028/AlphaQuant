"""
管理员接口，挂载在 /api/v1/admin 下（仅 is_admin=1 可访问）。

- GET  /users                 全部用户：最后访问、今天和累计的 AI 次数、回测数、是否停用
- POST /users/{id}/active     停用或恢复一个账户（管理员账户不能停用）
- GET  /stats                 平台的真实数字：用户、研究、AI 用量、邀请码、注册方式、备份
- GET  /registration          注册方式和全部邀请码
- PUT  /registration          改注册方式：open 开放 / invite 凭邀请码 / closed 暂停
- POST /invites               生成邀请码（可以指定码、次数和备注）
- POST /invites/{code}/active 停用或恢复页面生成的邀请码
- GET  /system                服务器状态：磁盘空间、数据占用、备份列表、财务数据的自动更新
- POST /backup                现在手动备份一次
- GET  /settings              系统设置：AI 模型、AI 次数、数据更新、邮件服务（密钥只显示前后几位）
- PUT  /settings              保存或清除系统设置（要再输一次管理员密码），立刻生效
- POST /settings/test         用页面上（可以还没保存）的设置测试文本模型、Jev 或发一封测试邮件
- GET  /audit                 管理员做过的操作
- GET  /ai-usage              最近 30 天每天各类 AI 的次数、token 用量、用得最多的用户
"""
import shutil
import time
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from ..database import get_conn
from ..quant import audit, backup, fundamentals_schedule, mailer, platform_ai, rate_limit, registration, site_config
from ..quant.runtime import MARKET_ROOT, RUNTIME_ROOT
from ..routes.auth import get_current_user
from ..security import verify_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


class ActiveIn(BaseModel):
    active: bool


class ModeIn(BaseModel):
    mode: str


class InviteIn(BaseModel):
    code: str = Field("", max_length=32, description="留空自动生成")
    max_uses: int | None = Field(None, ge=1, le=100000, description="最多注册几个人，留空不限")
    note: str = Field("", max_length=60, description="备注，例如发给谁")


@router.get("/users", dependencies=[Depends(require_admin)])
def list_users():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT u.id, u.name, u.email, u.created_at, u.is_admin, u.is_active, u.last_seen_at,
                   (SELECT COALESCE(SUM(a.count), 0) FROM ai_usage a WHERE a.user_id = u.id AND a.day = ?) AS ai_today,
                   (SELECT COALESCE(SUM(a.count), 0) FROM ai_usage a WHERE a.user_id = u.id) AS ai_total,
                   (SELECT COUNT(*) FROM backtests b WHERE b.user_id = u.id) AS backtests
            FROM users u ORDER BY u.id DESC
            """,
            (platform_ai._today(),),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "email": r["email"],
            "created_at": r["created_at"],
            "last_seen_at": r["last_seen_at"],
            "is_admin": bool(r["is_admin"]),
            "is_active": bool(r["is_active"]),
            "ai_today": int(r["ai_today"]),
            "ai_total": int(r["ai_total"]),
            "backtests": int(r["backtests"]),
        }
        for r in rows
    ]


@router.post("/users/{uid}/active")
def set_user_active(uid: int, body: ActiveIn, admin: dict = Depends(require_admin)):
    """停用：不能再登录，已经登录的设备立即失效；恢复：可以重新登录。账户里的数据都不动。"""

    with get_conn() as conn:
        row = conn.execute("SELECT is_admin, email FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="没有这个用户")
        if row["is_admin"]:
            raise HTTPException(status_code=403, detail="管理员账户不能停用")
        conn.execute("UPDATE users SET is_active = ?, token_version = token_version + ? WHERE id = ?",
                     (1 if body.active else 0, 0 if body.active else 1, uid))
    audit.record(admin, "user.enable" if body.active else "user.disable",
                 f"{'恢复' if body.active else '停用'}了账户 {row['email']}", user_id=uid)
    return {"id": uid, "is_active": body.active}


@router.get("/registration", dependencies=[Depends(require_admin)])
def registration_settings():
    return {"mode": registration.mode(), "locked": registration.env_locked(), "invites": registration.all_codes()}


MODE_NAMES = {"open": "开放注册", "invite": "凭邀请码注册", "closed": "暂停注册"}


@router.put("/registration")
def change_registration(body: ModeIn, admin: dict = Depends(require_admin)):
    registration.set_mode(body.mode)
    audit.record(admin, "registration.mode", f"注册方式改为“{MODE_NAMES.get(body.mode, body.mode)}”", mode=body.mode)
    return registration_settings()


@router.post("/invites", status_code=status.HTTP_201_CREATED)
def create_invite(body: InviteIn, admin: dict = Depends(require_admin)):
    code = registration.create_code(body.code, body.max_uses, body.note)
    audit.record(admin, "registration.invite", f"生成了邀请码 {code}（可用 {body.max_uses} 次）", code=code, note=body.note)
    return {"code": code, **registration_settings()}


@router.post("/invites/{code}/active")
def set_invite_active(code: str, body: ActiveIn, admin: dict = Depends(require_admin)):
    registration.set_code_active(code, body.active)
    audit.record(admin, "registration.invite_active", f"{'恢复' if body.active else '停用'}了邀请码 {code}", code=code)
    return registration_settings()


def _china_day_start() -> str:
    """今天（北京时间）0 点对应的 UTC 时间；数据库里的时间都是 UTC 的 ISO 文本，可以直接比较。"""

    start = datetime.now(platform_ai.CHINA).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat()


def _count(conn, sql: str, *args) -> int:
    return int(conn.execute(sql, args).fetchone()[0] or 0)


def _latest_backup() -> dict:
    root = backup.backup_root()
    folders = sorted(p.name for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")) if root.is_dir() else []
    return {"enabled": backup.enabled(), "latest": folders[-1] if folders else None, "count": len(folders), "keep": backup.keep()}


@router.get("/stats", dependencies=[Depends(require_admin)])
def admin_stats():
    today, since = platform_ai._today(), _china_day_start()
    with get_conn() as conn:
        users = {
            "total": _count(conn, "SELECT COUNT(*) FROM users"),
            "new_today": _count(conn, "SELECT COUNT(*) FROM users WHERE created_at >= ?", since),
            "active_today": _count(conn, "SELECT COUNT(*) FROM users WHERE last_seen_at >= ?", since),
        }
        research = {
            "backtests": _count(conn, "SELECT COUNT(*) FROM backtests"),
            "backtests_today": _count(conn, "SELECT COUNT(*) FROM backtests WHERE created_at >= ?", since),
            "strategies": _count(conn, "SELECT COUNT(*) FROM strategy_packages"),
            "briefs": _count(conn, "SELECT COUNT(*) FROM stock_briefs"),
            "briefs_today": _count(conn, "SELECT COUNT(*) FROM stock_briefs WHERE created_at >= ?", since),
        }
        by_kind = {r["kind"]: int(r["total"]) for r in conn.execute(
            "SELECT kind, SUM(count) AS total FROM ai_usage WHERE day = ? GROUP BY kind", (today,))}
        total_row = conn.execute("SELECT count FROM ai_usage_total WHERE day = ?", (today,)).fetchone()
        disabled = _count(conn, "SELECT COUNT(*) FROM users WHERE is_active = 0")
    words = {kind: word for kind, (_variable, _default, word) in platform_ai.LIMITS.items()}
    ai = {
        "day": today,
        "used": int(total_row["count"]) if total_row else 0,     # 含管理员的调用
        "limit": platform_ai.daily_total_limit(),
        "by_kind": [{"kind": kind, "label": words.get(kind, kind), "count": count} for kind, count in sorted(by_kind.items())],
    }
    invites = [item for item in registration.all_codes() if item["active"]]
    users["disabled"] = disabled
    return {
        "users": users,
        "research": research,
        "ai": ai,
        "registration": {"mode": registration.mode(), "invites": invites},
        "backup": _latest_backup(),
    }


# 磁盘剩余少于这么多就提醒：行情数据会越来越大，磁盘满了每日更新会失败。
DISK_WARN_BYTES = 5 * 1024 ** 3
DISK_WARN_SHARE = 0.10
SIZE_CACHE_SECONDS = 300
_size_cache: dict[str, tuple[float, int]] = {}


def _cached_size(path) -> int:
    """文件夹大小；行情数据有几千个文件，算一次要一会儿，5 分钟内用上次的结果。"""

    key = str(path)
    hit = _size_cache.get(key)
    if hit and time.monotonic() - hit[0] < SIZE_CACHE_SECONDS:
        return hit[1]
    size = backup.folder_size(path) if path.exists() else 0
    _size_cache[key] = (time.monotonic(), size)
    return size


def _disk() -> dict:
    target = MARKET_ROOT if MARKET_ROOT.exists() else RUNTIME_ROOT
    usage = shutil.disk_usage(target)
    low = usage.free < DISK_WARN_BYTES or usage.free < usage.total * DISK_WARN_SHARE
    return {"total": usage.total, "used": usage.used, "free": usage.free, "warning": low}


@router.get("/system", dependencies=[Depends(require_admin)])
def system_status():
    from ..routes.workspace import _data_jobs

    return {
        "disk": _disk(),
        "sizes": {"market": _cached_size(MARKET_ROOT), "runtime": _cached_size(RUNTIME_ROOT),
                  "backups": sum(item["size"] for item in backup.listing())},
        "backups": {**_latest_backup(), "items": backup.listing()},
        "fundamentals": fundamentals_schedule.status(_data_jobs().records()),
    }


@router.post("/backup", status_code=status.HTTP_201_CREATED)
def backup_now(user: dict = Depends(require_admin)):
    rate_limit.check(f"backup:{user['id']}", 6, 60 * 60, "备份太频繁")
    try:
        folder = backup.backup(manual=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"备份失败：{exc.strerror or exc}") from None
    audit.record(user, "backup.manual", f"手动备份了一次（{folder.name if folder else '没有新内容'}）")
    return {"name": folder.name if folder else None, "items": backup.listing()}


# --------------------------------------------------------------------------- #
# 系统设置
# --------------------------------------------------------------------------- #


class SettingsIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)     # 再输一次管理员密码
    values: dict[str, Any] = Field(default_factory=dict)
    clear: list[str] = Field(default_factory=list)               # 改回用 .env 的设置


class SettingsTestIn(BaseModel):
    target: Literal["text", "decision", "email"]
    values: dict[str, Any] = Field(default_factory=dict)         # 页面上还没保存的值；密钥留空表示用已保存的


PASSWORD_FAILURES = (5, 15 * 60)
TEST_LIMIT = (10, 10 * 60)


def _confirm_password(admin: dict, password: str) -> None:
    """Saving settings needs the admin password again, so an unattended session cannot change keys."""

    key = f"settings-password:{admin['id']}"
    rate_limit.check(key, *PASSWORD_FAILURES, "管理员密码输错太多次", record=False)
    with get_conn() as conn:
        row = conn.execute("SELECT password_hash, salt FROM users WHERE id = ?", (admin["id"],)).fetchone()
    if not row or not verify_password(password, row["salt"], row["password_hash"]):
        rate_limit.record(key, PASSWORD_FAILURES[1])
        raise HTTPException(status_code=403, detail="管理员密码不正确，设置没有保存")
    rate_limit.clear(key)


@router.get("/settings", dependencies=[Depends(require_admin)])
def settings_list():
    return site_config.describe()


@router.put("/settings")
def settings_save(body: SettingsIn, admin: dict = Depends(require_admin)):
    _confirm_password(admin, body.password)
    try:
        changed = site_config.update(body.values, body.clear)
    except site_config.SettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    if changed:
        labels = [site_config.BY_NAME[name].label for name in changed]
        cleared = [site_config.BY_NAME[name].label for name in body.clear]
        audit.record(admin, "settings.update", "修改了系统设置：" + "、".join(labels)
                     + (f"（其中改回用 .env：{'、'.join(cleared)}）" if cleared else ""), names=changed, cleared=body.clear)
    return {**site_config.describe(), "changed": changed}


@router.post("/settings/test")
def settings_test(body: SettingsTestIn, admin: dict = Depends(require_admin)):
    """Try the settings on the page (saved or not) once; nothing is saved and no user quota is used."""

    rate_limit.check(f"settings-test:{admin['id']}", *TEST_LIMIT, "测试太频繁")
    try:
        config = site_config.candidate(body.values)
    except site_config.SettingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    from .agent_lab import _ai_failure

    started = time.monotonic()
    try:
        if body.target == "text":
            model = platform_ai.platform_model(config)
            if model is None:
                raise HTTPException(status_code=422, detail="还没有填文本模型的密钥（或 OpenRouter 密钥）")
            reply = platform_ai.model_client(model).chat([{"role": "user", "content": "这是连接测试，请只回复两个字：收到"}],
                                                         temperature=0, max_tokens=10)
            result = {"model": reply.model or model.model, "reply": reply.text.strip()[:40]}
        elif body.target == "decision":
            from quant_platform.jev.client import choice_question

            client = platform_ai.decision_client(config)
            if client is None:
                raise HTTPException(status_code=422, detail="还没有填 TypeSafe Jev 密钥（或 OpenRouter 密钥）")
            client.ask({"测试": "连接检查"}, {"ok": choice_question("这是连接测试，请选“正常”。", {"正常": "连接正常", "异常": "连接异常"})})
            result = {"model": getattr(client, "served_model", None) or client.model}
        else:
            if not mailer.configured(config):
                raise HTTPException(status_code=422, detail="还没有填 SMTP 服务器和发件人地址")
            mailer.send_mail(admin["email"], "【镜思】测试邮件", "这是管理后台发出的测试邮件。收到说明邮件服务配置正确，找回密码可以正常发验证码。", config)
            result = {"to": admin["email"]}
            audit.record(admin, "settings.test_email", f"发了一封测试邮件到 {admin['email']}")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 把原因翻成看得懂的话
        reason = "邮件发送失败，请检查服务器、端口、账号和授权码" if body.target == "email" else _ai_failure(exc)
        return {"ok": False, "message": reason, "seconds": round(time.monotonic() - started, 1)}
    return {"ok": True, "seconds": round(time.monotonic() - started, 1), **result}


@router.get("/audit", dependencies=[Depends(require_admin)])
def audit_list(kind: str = Query("", max_length=20), limit: int = Query(100, ge=1, le=audit.MAX_ROWS)):
    return {"items": audit.listing(kind, limit), "kinds": audit.KINDS}


@router.get("/ai-usage", dependencies=[Depends(require_admin)])
def ai_usage(days: int = Query(30, ge=1, le=90)):
    return platform_ai.usage_history(days)
