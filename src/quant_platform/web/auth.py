"""本地用户认证：SQLite 用户表 + PBKDF2 密码哈希。"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from dataclasses import dataclass
from pathlib import Path


DEFAULT_AUTH_DB = Path("data") / "fellowquant_auth.sqlite3"
_LEGACY_AUTH_DB = Path("data") / "alphaquant_auth.sqlite3"
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-]{3,32}$")
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_HASH_ALGORITHM = "pbkdf2_sha256"
_HASH_ITERATIONS = 310_000


@dataclass(frozen=True)
class AuthResult:
    """认证操作结果。"""

    ok: bool
    message: str
    username: str = ""


class AuthStore:
    """保存和校验本地用户。密码只保存带随机盐的 PBKDF2 哈希。"""

    def __init__(self, db_path: str | Path = DEFAULT_AUTH_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_db()
        self._initialize()

    def _migrate_legacy_db(self) -> None:
        """品牌更名后自动接管旧版 AlphaQuant 用户库，避免老用户丢失。"""

        if (
            self.db_path == DEFAULT_AUTH_DB
            and not self.db_path.exists()
            and _LEGACY_AUTH_DB.exists()
        ):
            try:
                _LEGACY_AUTH_DB.replace(self.db_path)
            except OSError:
                # 迁移失败时退回旧库继续可用。
                self.db_path = _LEGACY_AUTH_DB

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            _HASH_ITERATIONS,
        )
        return "$".join(
            (
                _HASH_ALGORITHM,
                str(_HASH_ITERATIONS),
                salt.hex(),
                digest.hex(),
            )
        )

    @staticmethod
    def _verify_password(password: str, encoded: str) -> bool:
        try:
            algorithm, iterations_text, salt_hex, digest_hex = encoded.split("$", 3)
            if algorithm != _HASH_ALGORITHM:
                return False
            iterations = int(iterations_text)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except (TypeError, ValueError):
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)

    def register(self, username: str, email: str, password: str, confirmation: str) -> AuthResult:
        username = username.strip()
        email = email.strip().lower()
        if not _USERNAME_RE.fullmatch(username):
            return AuthResult(False, "用户名需为 3-32 位字母、数字、下划线或连字符。")
        if not _EMAIL_RE.fullmatch(email):
            return AuthResult(False, "请输入合法的邮箱地址。")
        if len(password) < 8:
            return AuthResult(False, "密码至少需要 8 位。")
        if password != confirmation:
            return AuthResult(False, "两次输入的密码不一致。")
        connection = self._connect()
        try:
            connection.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, self._hash_password(password)),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            return AuthResult(False, "用户名或邮箱已经注册。")
        finally:
            connection.close()
        return AuthResult(True, "注册成功，请使用新账号登录。", username=username)

    def authenticate(self, identity: str, password: str) -> AuthResult:
        identity = identity.strip()
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT username, password_hash
                FROM users
                WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
                LIMIT 1
                """,
                (identity, identity),
            ).fetchone()
        finally:
            connection.close()
        if row is None or not self._verify_password(password, row["password_hash"]):
            return AuthResult(False, "邮箱/用户名或密码不正确。")
        return AuthResult(True, "登录成功。", username=str(row["username"]))
