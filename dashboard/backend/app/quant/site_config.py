"""Settings the administrator can change in the admin console instead of ``.env``.

Each setting keeps the name of its environment variable. A value saved in the console is written
into this process's environment, so every existing ``os.getenv`` read and every data job started
afterwards (child processes inherit the environment) sees it at once, with no restart. Clearing a
value puts back what ``.env`` had when the backend started.

Saved values live in ``site_settings`` under ``config:<NAME>``. Keys and passwords are encrypted
with a key derived from ``APP_SECRET``; they are never sent back to the browser, only their first
and last characters. If ``APP_SECRET`` changes, the saved secrets cannot be read any more and are
reported as such, so the administrator can enter them again.

Settings that must be fixed before the backend starts or that guard the server itself
(``APP_SECRET``, the first administrator, data directories, ports) stay in ``.env`` only.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import re
import threading
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken

from quant_platform.data.providers.baostock_provider import DEFAULT_INTERVAL

from ..database import get_conn
from ..security import SECRET_KEY
from . import points
from .daily_schedule import DEFAULT_TIME
from .platform_ai import DEFAULT_BASE_URL, DEFAULT_MODEL, LIMITS, TOTAL_DEFAULT

PREFIX = "config:"


@dataclass(frozen=True)
class Setting:
    name: str                    # 环境变量名
    group: str
    label: str
    kind: str                    # secret / text / url / int / number / switch / time / email
    help: str = ""
    default: str = ""            # 没有设置时程序实际用的值（只用来显示）
    minimum: float | None = None
    maximum: float | None = None
    options: tuple[str, ...] = field(default_factory=tuple)


GROUPS = {
    "ai": "AI 模型",
    "limits": "每天免费次数",
    "points": "积分",
    "data": "数据更新",
    "mail": "邮件服务（找回密码）",
}

SETTINGS: tuple[Setting, ...] = (
    Setting("OPENROUTER_API_KEY", "ai", "OpenRouter 密钥", "secret",
            "文本模型和决策模型 Jev 都可以用这个密钥；下面没有单独填的，就用它。"),
    Setting("FELLOWQUANT_AI_BASE_URL", "ai", "文本模型接口地址", "url",
            "OpenAI 兼容的接口地址。用 OpenRouter 时留空。", default=DEFAULT_BASE_URL),
    Setting("FELLOWQUANT_AI_MODEL", "ai", "文本模型名称", "text",
            "AI 解读、追问、AI 问答、一句话生成规则用的模型。", default=DEFAULT_MODEL),
    Setting("FELLOWQUANT_AI_API_KEY", "ai", "文本模型密钥", "secret",
            "不用 OpenRouter 时填写（例如 DeepSeek、通义千问的密钥）；留空就用 OpenRouter 密钥。"),
    Setting("TYPESAFE_API_KEY", "ai", "TypeSafe Jev 密钥", "secret",
            "决策模型 Jev 的官方密钥；留空时通过 OpenRouter 调用 Jev。"),
    Setting("FELLOWQUANT_JEV_MODEL", "ai", "Jev 模型名称", "text", "一般留空，用默认的版本。"),
    Setting("FELLOWQUANT_JEV_URL", "ai", "Jev 接口地址", "url", "一般留空，用默认的地址。"),

    *(Setting(variable, "limits", f"{word}（每人每天免费）", "int", "免费次数用完以后每次扣积分。",
              default=str(default), minimum=0, maximum=10000)
      for variable, default, word in LIMITS.values()),
    Setting("FELLOWQUANT_AI_DAILY_TOTAL", "limits", "全站每天最多（所有人加起来）", "int",
            "所有用户、所有种类加起来；管理员的调用计入但不受限制。0 表示不限。", default=str(TOTAL_DEFAULT), minimum=0, maximum=1000000),

    Setting(points.SIGNUP[0], "points", "新用户赠送积分", "int",
            "每个账户只送一次；以前注册的账户第一次打开时补上。0 表示不送。", default=str(points.SIGNUP[1]), minimum=0, maximum=100000),
    Setting(points.GIFT_DAYS[0], "points", "赠送的积分多少天有效", "int", default=str(points.GIFT_DAYS[1]), minimum=1, maximum=3650),
    Setting(points.DAILY_CAP[0], "points", "每人每天最多用几次 AI（免费的加积分的）", "int",
            "防止一个账户一直调用。0 表示不限。", default=str(points.DAILY_CAP[1]), minimum=0, maximum=100000),
    *(Setting(variable, "points", f"{LIMITS[kind][2]}：每次多少积分", "int", default=str(default), minimum=1, maximum=10000)
      for kind, (variable, default) in points.COSTS.items()),

    Setting("FELLOWQUANT_DAILY_UPDATE", "data", "每个交易日自动更新", "switch", default="on", options=("on", "off")),
    Setting("FELLOWQUANT_DAILY_UPDATE_TIME", "data", "自动更新的时间（北京时间）", "time",
            "收盘后的数据要到 18:30 左右才齐。", default=DEFAULT_TIME.strftime("%H:%M")),
    Setting("FELLOWQUANT_FUNDAMENTALS_UPDATE", "data", "财报季自动更新财务数据", "switch", default="on", options=("on", "off")),
    Setting("FELLOWQUANT_BAOSTOCK_INTERVAL", "data", "BaoStock 两次请求之间至少间隔（秒）", "number",
            "调大可以降低被数据源拉黑的可能，下载会变慢。对之后启动的任务生效。", default=str(DEFAULT_INTERVAL), minimum=0, maximum=5),

    Setting("SMTP_HOST", "mail", "SMTP 服务器", "text", "例如 smtp.qq.com。"),
    Setting("SMTP_PORT", "mail", "端口", "int", "使用 STARTTLS，一般是 587。", default="587", minimum=1, maximum=65535),
    Setting("SMTP_USERNAME", "mail", "账号", "text"),
    Setting("SMTP_PASSWORD", "mail", "密码或授权码", "secret"),
    Setting("SMTP_FROM", "mail", "发件人地址", "email"),
)
BY_NAME = {setting.name: setting for setting in SETTINGS}

# 后端启动时 .env（和系统环境变量）里原来的值：清除后台设置时还原成这些。
_ORIGINAL: dict[str, str | None] = {setting.name: os.environ.get(setting.name) for setting in SETTINGS}
_LOCK = threading.Lock()


class SettingError(ValueError):
    """A value the administrator can fix; the message is shown as-is."""


# --------------------------------------------------------------------------- #
# 加密
# --------------------------------------------------------------------------- #


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"fellowquant-site-config:" + SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _seal(value: str) -> str:
    return "enc:" + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def _open(stored: str) -> str | None:
    """The plain value; ``None`` when it was encrypted with another ``APP_SECRET``."""

    if not stored.startswith("enc:"):
        return stored
    try:
        return _fernet().decrypt(stored[4:].encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def mask(value: str) -> str:
    """``sk-or-v1-1234…cdef``: enough to recognise a key, never enough to use it."""

    value = value or ""
    if len(value) <= 8:
        return "已设置" if value else ""
    return f"{value[:4]}…{value[-4:]}"


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #


def _saved() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM site_settings WHERE key LIKE ?", (PREFIX + "%",)).fetchall()
    return {row["key"][len(PREFIX):]: row["value"] for row in rows if row["key"][len(PREFIX):] in BY_NAME}


def apply(names: list[str] | None = None) -> None:
    """Put the saved values into the environment; a name in ``names`` with nothing saved gets its ``.env``
    value back. With no ``names`` (at start-up) only the saved settings are touched."""

    saved = _saved()
    with _LOCK:
        for name in (names if names is not None else list(saved)):
            value = _open(saved[name]) if name in saved else None
            if value is not None:
                os.environ[name] = value
            elif _ORIGINAL.get(name) is not None:
                os.environ[name] = _ORIGINAL[name]
            else:
                os.environ.pop(name, None)


def _url(value: str, label: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SettingError(f"{label}必须是 http:// 或 https:// 开头的网址")
    host = parsed.hostname
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    # 只有本机地址可以用 http；连别的服务器必须用 https，免得密钥在网上明文传输。
    local = host == "localhost" or (address is not None and address.is_loopback)
    if parsed.scheme == "http" and not local:
        raise SettingError(f"{label}连接其他服务器时必须用 https://，免得密钥被明文传输")
    return value.rstrip("/")


def clean(setting: Setting, raw: Any) -> str:
    """The value as stored, or :class:`SettingError` with a readable reason."""

    value = str(raw if raw is not None else "").strip()
    if len(value) > 500:
        raise SettingError(f"{setting.label}太长了")
    if not value:
        raise SettingError(f"{setting.label}不能为空；不想用后台的设置时，点“改回用 .env”")
    if setting.kind == "url":
        return _url(value, setting.label)
    if setting.kind in ("int", "number"):
        try:
            number = int(value) if setting.kind == "int" else float(value)
        except ValueError:
            raise SettingError(f"{setting.label}必须是{'整数' if setting.kind == 'int' else '数字'}") from None
        if (setting.minimum is not None and number < setting.minimum) or (setting.maximum is not None and number > setting.maximum):
            raise SettingError(f"{setting.label}要在 {setting.minimum:g} 到 {setting.maximum:g} 之间")
        return str(number)
    if setting.kind == "switch":
        if value not in setting.options:
            raise SettingError(f"{setting.label}只能是开或关")
        return value
    if setting.kind == "time":
        match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
        if not match or int(match[1]) > 23 or int(match[2]) > 59:
            raise SettingError(f"{setting.label}的格式是 时:分，例如 18:30")
        return f"{int(match[1]):02d}:{match[2]}"
    if setting.kind == "email":
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise SettingError(f"{setting.label}格式不对")
        return value
    if any(ch in value for ch in "\r\n"):
        raise SettingError(f"{setting.label}不能换行")
    return value


def update(values: dict[str, Any], clear: list[str]) -> list[str]:
    """Save ``values`` (blank secrets are left as they are) and drop ``clear``; returns what changed."""

    unknown = [name for name in [*values, *clear] if name not in BY_NAME]
    if unknown:
        raise SettingError(f"不认识的设置：{'、'.join(unknown)}")
    cleaned: dict[str, str] = {}
    for name, raw in values.items():
        setting = BY_NAME[name]
        if setting.kind == "secret" and not str(raw or "").strip():
            continue                                    # 密钥留空表示不修改
        cleaned[name] = clean(setting, raw)
    changed = sorted(set(cleaned) | set(clear))
    with get_conn() as conn:
        for name, value in cleaned.items():
            stored = _seal(value) if BY_NAME[name].kind == "secret" else value
            conn.execute("INSERT INTO site_settings (key, value) VALUES (?, ?) "
                         "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (PREFIX + name, stored))
        for name in clear:
            conn.execute("DELETE FROM site_settings WHERE key = ?", (PREFIX + name,))
    apply(changed)
    return changed


def effective(name: str) -> str:
    """What the program uses right now (after :func:`apply`)."""

    return os.environ.get(name, "").strip()


def describe() -> dict[str, Any]:
    """Every setting for the admin page: value (secrets masked), where it comes from, and its rules."""

    saved = _saved()
    groups: dict[str, list[dict[str, Any]]] = {key: [] for key in GROUPS}
    for setting in SETTINGS:
        stored = saved.get(setting.name)
        plain = _open(stored) if stored is not None else None
        unreadable = stored is not None and plain is None
        original = (_ORIGINAL.get(setting.name) or "").strip()
        source = "admin" if plain is not None else "env" if original else "default"
        current = plain if plain is not None else original
        item = {
            "name": setting.name, "label": setting.label, "kind": setting.kind, "help": setting.help,
            "default": setting.default, "source": source, "env_set": bool(original), "unreadable": unreadable,
            "minimum": setting.minimum, "maximum": setting.maximum, "options": list(setting.options),
        }
        if setting.kind == "secret":
            item.update(value="", masked=mask(current), configured=bool(current))
        else:
            item.update(value=current, configured=bool(current))
        groups[setting.group].append(item)
    return {"groups": [{"key": key, "label": label, "items": groups[key]} for key, label in GROUPS.items()]}


def candidate(values: dict[str, Any]) -> dict[str, str]:
    """The settings as they would be if ``values`` (not yet saved) were applied: for testing first."""

    result = {name: effective(name) for name in BY_NAME}
    for name, raw in (values or {}).items():
        if name not in BY_NAME:
            continue
        setting = BY_NAME[name]
        if setting.kind == "secret" and not str(raw or "").strip():
            continue
        if str(raw or "").strip():
            result[name] = clean(setting, raw)
    return result
