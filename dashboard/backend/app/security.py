"""
安全工具：密码哈希 + 令牌签发/校验。

全部使用 Python 标准库（hashlib / hmac / secrets / json / time），
不引入 passlib / python-jose 等额外依赖。

- 密码：PBKDF2-HMAC-SHA256，10 万次迭代，每用户独立盐。
- 令牌：自签 HMAC-SHA256 的 payload.exp.signature 三段式（类似 JWT），
  7 天有效期，服务端用 SECRET_KEY 校验签名。
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

def _load_secret() -> str:
    configured = os.getenv("APP_SECRET", "").strip()
    if configured:
        return configured
    data_dir = Path(os.getenv("FELLOWQUANT_DATA_DIR") or Path(__file__).resolve().parents[1] / "data")
    path = data_dir / "runtime/app-secret.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another worker may still be writing the newly created file.
        for _ in range(50):
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
            time.sleep(0.02)
        raise RuntimeError("签名密钥文件为空，请检查 data/runtime/app-secret.key")
    value = secrets.token_hex(32)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(value)
    return value


SECRET_KEY = _load_secret()
ITERATIONS = 100_000
TOKEN_TTL = 7 * 24 * 3600  # 7 天


def hash_password(password: str, salt: str) -> str:
    """返回 PBKDF2 十六进制哈希。"""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS
    ).hex()


def gen_salt() -> str:
    return secrets.token_hex(16)


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    """恒定时间比较，避免计时攻击。"""
    actual = hash_password(password, salt)
    return hmac.compare_digest(actual, expected_hash)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def create_token(user_id: int, name: str, version: int = 0) -> str:
    """签发令牌。"""
    payload = {
        "uid": user_id,
        "name": name,
        "ver": version,
        "iat": int(time.time()),
        "exp": int(time.time()) + TOKEN_TTL,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(SECRET_KEY.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return f"{_b64(payload_bytes)}.{_b64(sig)}"


def decode_token(token: str) -> dict | None:
    """校验并解码令牌，失败/过期返回 None。"""
    try:
        payload_b64, sig_b64 = token.split(".")
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
        sig = base64.urlsafe_b64decode(sig_b64 + "==")
        expected = hmac.new(
            SECRET_KEY.encode("utf-8"), payload_bytes, hashlib.sha256
        ).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(payload_bytes)
        if not isinstance(payload, dict) or type(payload.get("uid")) is not int or payload["uid"] < 1:
            return None
        if payload.get("exp", 0) <= time.time():
            return None
        return payload
    except Exception:
        return None
