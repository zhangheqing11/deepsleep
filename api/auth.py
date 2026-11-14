"""Minimal in-memory bearer authentication for the local demo."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import scrypt, sha256
import hmac
import secrets
import time
from typing import Literal

from fastapi import Request

from api.config import Settings
from api.errors import APIError


@dataclass(frozen=True)
class AuthUser:
    id: str
    display_name: str
    role: Literal["operator", "user"] = "operator"


@dataclass(frozen=True)
class _TokenRecord:
    user: AuthUser
    expires_at: float


ANONYMOUS_USER = AuthUser(id="anonymous", display_name="匿名演示")

# 自助注册的演示账号只存在进程内存里：重启即清空，不落盘。上限防止内存被填满。
MAX_REGISTERED_ACCOUNTS = 200


@dataclass(frozen=True)
class _Account:
    user: AuthUser
    salt: bytes
    digest: bytes


def _account_digest(password: str, salt: bytes) -> bytes:
    """Salted scrypt for self-registered accounts (the configured demo account keeps its SHA-256 env digest)."""
    return scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)


def password_digest(password: str) -> str:
    return sha256(password.encode("utf-8")).hexdigest()


class AuthService:
    """Issue opaque, process-local tokens for the local demo.

    Tokens disappear on restart, there is one configured demo account, and no
    user data is persisted. This is deliberately not a production identity
    system.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._tokens: dict[str, _TokenRecord] = {}
        self._accounts: dict[str, _Account] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.auth_mode == "demo"

    def login(self, username: str, password: str) -> tuple[str, AuthUser, int]:
        if not self.enabled:
            raise APIError(503, "AUTH_DISABLED", "当前服务未启用登录。")
        valid_user = hmac.compare_digest(username, self.settings.auth_username)
        supplied_digest = password_digest(password)
        valid_password = hmac.compare_digest(supplied_digest, self.settings.auth_password_sha256)
        if not (valid_user and valid_password):
            account = self._accounts.get(username.casefold())
            if account is None or not hmac.compare_digest(_account_digest(password, account.salt), account.digest):
                raise APIError(401, "INVALID_CREDENTIALS", "用户名或密码错误。")
            return self._issue(account.user)
        return self._issue(AuthUser(id=self.settings.auth_username, display_name="演示用户"))

    def register(self, username: str, password: str, display_name: str | None) -> tuple[str, AuthUser, int]:
        """Create an in-memory demo account and sign it in. Nothing is persisted."""
        if not self.enabled:
            raise APIError(503, "AUTH_DISABLED", "当前服务未启用登录。")
        key = username.casefold()
        if key == self.settings.auth_username.casefold() or key in self._accounts:
            raise APIError(409, "USERNAME_TAKEN", "这个账号已经有人用了。")
        if len(self._accounts) >= MAX_REGISTERED_ACCOUNTS:
            raise APIError(503, "REGISTRATION_FULL", "演示账号数量已达上限。")
        salt = secrets.token_bytes(16)
        user = AuthUser(id=username, display_name=(display_name or "").strip() or username, role="user")
        self._accounts[key] = _Account(user=user, salt=salt, digest=_account_digest(password, salt))
        return self._issue(user)

    def _issue(self, user: AuthUser) -> tuple[str, AuthUser, int]:
        token = secrets.token_urlsafe(32)
        self._tokens[token] = _TokenRecord(user=user, expires_at=time.time() + self.settings.auth_ttl_s)
        return token, user, self.settings.auth_ttl_s

    def authenticate(self, authorization: str | None) -> AuthUser:
        if not self.enabled:
            return ANONYMOUS_USER
        if not authorization or not authorization.startswith("Bearer "):
            raise APIError(401, "AUTH_REQUIRED", "请先登录后再访问此接口。")
        token = authorization[7:].strip()
        record = self._tokens.get(token)
        if record is None:
            raise APIError(401, "INVALID_TOKEN", "登录状态无效，请重新登录。")
        if record.expires_at <= time.time():
            self._tokens.pop(token, None)
            raise APIError(401, "TOKEN_EXPIRED", "登录状态已过期，请重新登录。")
        return record.user

    def logout(self, authorization: str | None) -> None:
        if not self.enabled:
            return
        if not authorization or not authorization.startswith("Bearer "):
            raise APIError(401, "AUTH_REQUIRED", "请先登录后再操作。")
        token = authorization[7:].strip()
        if token not in self._tokens:
            raise APIError(401, "INVALID_TOKEN", "登录状态无效，请重新登录。")
        self._tokens.pop(token, None)


def current_user(request: Request) -> AuthUser:
    return request.app.state.auth.authenticate(request.headers.get("Authorization"))
