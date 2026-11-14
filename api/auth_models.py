"""Authentication API models; credentials are never returned or logged."""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=6, max_length=256)
    display_name: str | None = Field(default=None, max_length=20)


class UserPublic(BaseModel):
    id: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserPublic


class MeResponse(BaseModel):
    authenticated: bool
    user: UserPublic | None


class LogoutResponse(BaseModel):
    status: str = "ok"
