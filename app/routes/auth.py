from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from app.core.config import Settings
from app.models.user import User
from app.routes.dependencies import Database, get_settings, require_current_user
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_days * 86400,
        httponly=True,
        samesite="lax",
        secure=settings.is_cookie_secure,
        path="/",
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: Database,
    request: Request,
    response: Response,
):
    settings = get_settings(request)
    user = auth_service.register_user(session, data)
    _, raw_token = auth_service.create_session(session, user.id, settings.session_ttl_days)
    _set_session_cookie(response, raw_token, settings)
    return user


@router.post("/login", response_model=UserRead)
def login(
    data: LoginRequest,
    session: Database,
    request: Request,
    response: Response,
):
    settings = get_settings(request)
    user = auth_service.authenticate_user(session, data.email, data.password)
    _, raw_token = auth_service.create_session(session, user.id, settings.session_ttl_days)
    _set_session_cookie(response, raw_token, settings)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    session: Database,
):
    settings = get_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        auth_service.revoke_session(session, raw_token)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.is_cookie_secure,
    )
    return None


@router.get("/me", response_model=UserRead)
def get_current_user_profile(
    user: Annotated[User, Depends(require_current_user)],
):
    return user
