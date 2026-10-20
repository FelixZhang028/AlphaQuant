"""Send an email through the configured SMTP server (password reset codes, the admin's test email).

The settings come from the environment (``.env`` or the admin console), or from ``config`` when the
admin page tests values that are not saved yet. STARTTLS is always used.
"""

from __future__ import annotations

import os
import smtplib
from collections.abc import Mapping
from email.message import EmailMessage

TIMEOUT_SECONDS = 15


def _value(config: Mapping[str, str] | None, name: str, default: str = "") -> str:
    return str((os.environ if config is None else config).get(name, "") or "").strip() or default


def configured(config: Mapping[str, str] | None = None) -> bool:
    return bool(_value(config, "SMTP_HOST") and _value(config, "SMTP_FROM"))


def send_mail(to: str, subject: str, body: str, config: Mapping[str, str] | None = None) -> None:
    """Raises on any failure; callers turn that into a message for the user."""

    if not configured(config):
        raise RuntimeError("邮件服务还没有配置")
    mail = EmailMessage()
    mail["Subject"] = subject
    mail["From"] = _value(config, "SMTP_FROM")
    mail["To"] = to
    mail.set_content(body)
    with smtplib.SMTP(_value(config, "SMTP_HOST"), int(_value(config, "SMTP_PORT", "587")), timeout=TIMEOUT_SECONDS) as server:
        server.starttls()
        if _value(config, "SMTP_USERNAME"):
            server.login(_value(config, "SMTP_USERNAME"), _value(config, "SMTP_PASSWORD"))
        server.send_message(mail)
