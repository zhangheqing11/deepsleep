"""Demo account authentication endpoints."""

from typing import Annotated

from fastapi import APIRouter, Header, Request

from api.auth import current_user
from api.auth_models import LoginRequest, LoginResponse, LogoutResponse, MeResponse, UserPublic

router = APIRouter(prefix="/api/v1/auth", tags=["登录"])


def public_user(user) -> UserPublic:
    return UserPublic(id=user.id, display_name=user.display_name, role=user.role)


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request) -> LoginResponse:
    token, user, expires_in = request.app.state.auth.login(body.username, body.password)
    return LoginResponse(access_token=token, expires_in=expires_in, user=public_user(user))


@router.get("/me", response_model=MeResponse)
async def me(request: Request) -> MeResponse:
    if not request.app.state.auth.enabled:
        return MeResponse(authenticated=False, user=None)
    user = current_user(request)
    return MeResponse(authenticated=True, user=public_user(user))


@router.post("/logout", response_model=LogoutResponse)
async def logout(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> LogoutResponse:
    request.app.state.auth.logout(authorization)
    return LogoutResponse()
