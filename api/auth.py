"""Minimal in-memory bearer authentication for the local demo."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
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
    role: Literal["operator"] = "operator"


@dataclass(frozen=True)
class _TokenRecord:
    user: AuthUser
    expires_at: float


ANONYMOUS_USER = AuthUser(id="anonymous", display_name="匿名演示")


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
            raise APIError(401, "INVALID_CREDENTIALS", "用户名或密码错误。")
        token = secrets.token_urlsafe(32)
        expires_at = time.time() + self.settings.auth_ttl_s
        user = AuthUser(id=self.settings.auth_username, display_name="演示用户")
        self._tokens[token] = _TokenRecord(user=user, expires_at=expires_at)
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
