"""
认证 REST 接口，挂载在 /api/v1/auth 下。

- POST /register          官网注册 → 写入 SQLite users 表
- POST /login             登录校验 → 返回签名令牌
- POST /forgot/request    忘记密码：校验账号名+邮箱 → 生成随机验证码
- POST /forgot/reset      忘记密码：校验验证码 → 重置密码
- GET  /me                凭令牌获取当前用户信息（功能台鉴权守卫调用）
"""
import hmac
import os
import smtplib
from email.message import EmailMessage
import re
import secrets
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from ..database import get_conn
from ..security import (
    create_token,
    decode_token,
    gen_salt,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# 忘记密码验证码（内存存储）：{user_id: (code, expires_at, attempts)}
_RESET_CODES: dict[int, tuple[str, float, int]] = {}
RESET_CODE_TTL = 10 * 60          # 验证码有效期：10 分钟
RESET_CODE_MAX_ATTEMPTS = 5       # 验证码最多可尝试次数


class RegisterIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=40, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=8, description="密码至少 8 位")


class LoginIn(BaseModel):
    email: str = Field(..., description="邮箱")
    password: str = Field(..., description="密码")


class UserOut(BaseModel):
    id: int
    name: str
    email: str
    created_at: str
    is_admin: bool = False


def _user_to_out(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "created_at": row["created_at"],
        "is_admin": bool(row["is_admin"]) if "is_admin" in row.keys() else False,
    }


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """依赖项：从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录或令牌缺失")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌无效或已过期")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, email, created_at, is_admin, token_version FROM users WHERE id = ?", (payload["uid"],)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在")
    if payload.get("ver", 0) != row["token_version"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="登录已失效，请重新登录")
    return _user_to_out(row)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not _EMAIL_RE.match(body.email.strip()):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    salt = gen_salt()
    pwd_hash = hash_password(body.password, salt)
    now = datetime.now(timezone.utc).isoformat()
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO users (name, email, password_hash, salt, created_at) VALUES (?,?,?,?,?)",
                (body.name.strip(), body.email.strip().lower(), pwd_hash, salt, now),
            )
            uid = cur.lastrowid
            row = conn.execute(
                "SELECT id, name, email, created_at, is_admin FROM users WHERE id = ?", (uid,)
            ).fetchone()
    except Exception as e:  # 唯一约束冲突
        if "UNIQUE" in str(e).upper():
            raise HTTPException(status_code=409, detail="该邮箱已被注册")
        raise
    return _user_to_out(row)


@router.post("/login")
def login(body: LoginIn):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, name, email, password_hash, salt, created_at, is_admin, token_version FROM users WHERE email = ?",
            (body.email.strip().lower(),),
        ).fetchone()
    if not row or not verify_password(body.password, row["salt"], row["password_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")
    token = create_token(row["id"], row["name"], row["token_version"])
    return {"token": token, "user": _user_to_out(row)}


class ForgotRequestIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=40, description="账号名")
    email: str = Field(..., description="邮箱")


class ForgotResetIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=40, description="账号名")
    email: str = Field(..., description="邮箱")
    code: str = Field(..., min_length=4, max_length=8, description="验证码")
    new_password: str = Field(..., min_length=8, description="新密码至少 8 位")


def _find_user_by_name_email(name: str, email: str):
    """按账号名 + 邮箱查找用户（邮箱不区分大小写）。"""
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, name, email FROM users WHERE email = ? AND name = ? COLLATE NOCASE",
            (email.lower(), name.strip()),
        ).fetchone()


@router.post("/forgot/request")
def forgot_request(body: ForgotRequestIn):
    """Send reset codes to the registered mailbox; never expose codes in API responses."""
    if not os.getenv("SMTP_HOST") or not os.getenv("SMTP_FROM"):
        raise HTTPException(status_code=503, detail="密码重置邮件服务尚未配置，请联系管理员")
    if not _EMAIL_RE.match(body.email.strip()):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    row = _find_user_by_name_email(body.name, body.email.strip())
    message = {"message": "如果账号信息匹配，验证码将发送至注册邮箱", "expires_in": RESET_CODE_TTL}
    if not row:
        return message
    previous = _RESET_CODES.get(row["id"])
    if previous and previous[1] - RESET_CODE_TTL > time.time() - 60:
        raise HTTPException(status_code=429, detail="请等待一分钟后重新获取验证码")
    code = f"{secrets.randbelow(1000000):06d}"
    mail = EmailMessage()
    mail["Subject"] = "FellowQuant 密码重置验证码"
    mail["From"] = os.environ["SMTP_FROM"]
    mail["To"] = row["email"]
    mail.set_content(f"您的验证码是 {code}，10 分钟内有效。若非本人操作，请忽略此邮件。")
    try:
        with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.getenv("SMTP_PORT", "587")), timeout=15) as server:
            server.starttls()
            if os.getenv("SMTP_USERNAME"):
                server.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
            server.send_message(mail)
    except Exception:
        raise HTTPException(status_code=503, detail="验证码邮件发送失败，请稍后重试") from None
    _RESET_CODES[row["id"]] = (code, time.time() + RESET_CODE_TTL, 0)
    return message



@router.post("/forgot/reset")
def forgot_reset(body: ForgotResetIn):
    """忘记密码第二步：校验验证码并重置密码。"""
    row = _find_user_by_name_email(body.name, body.email)
    if not row:
        raise HTTPException(status_code=400, detail="账号名与邮箱不匹配，请核对后重试")
    entry = _RESET_CODES.get(row["id"])
    if not entry:
        raise HTTPException(status_code=400, detail="请先获取验证码")
    code, expires_at, attempts = entry
    if time.time() > expires_at:
        _RESET_CODES.pop(row["id"], None)
        raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
    if attempts >= RESET_CODE_MAX_ATTEMPTS:
        _RESET_CODES.pop(row["id"], None)
        raise HTTPException(status_code=400, detail="验证码错误次数过多，请重新获取")
    if not hmac.compare_digest(code, body.code.strip()):
        _RESET_CODES[row["id"]] = (code, expires_at, attempts + 1)
        raise HTTPException(status_code=400, detail="验证码错误")
    # 验证通过：清除验证码并用新盐更新密码
    _RESET_CODES.pop(row["id"], None)
    salt = gen_salt()
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ?, salt = ?, token_version = token_version + 1 WHERE id = ?",
            (hash_password(body.new_password, salt), salt, row["id"]),
        )
    return {"message": "密码重置成功，请使用新密码登录"}


@router.get("/me", response_model=UserOut, dependencies=[Depends(get_current_user)])
def me(current: dict = Depends(get_current_user)):
    return current
