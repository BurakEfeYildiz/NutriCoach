from collections.abc import Iterator
import hashlib
import hmac
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.auth import AuthSession
from app.models.user import User
from app.services.auth_service import validate_session_token


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


Database = Annotated[Session, Depends(get_session)]


def get_settings(request: Request) -> Settings:
    return getattr(request.app.state, "settings", None) or Settings()


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_current_user_optional(request: Request, session: Database) -> User | None:
    settings = get_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if not raw_token:
        return None

    result = validate_session_token(session, raw_token)
    if result is None:
        return None

    auth_session, user = result
    request.state.auth_session = auth_session
    request.state.current_user = user
    return user


def require_current_user(user: Annotated[User | None, Depends(get_current_user_optional)]) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Oturum açmanız gerekiyor.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_csrf_token_for_session(auth_session: AuthSession, settings: Settings) -> str:
    secret = settings.csrf_secret.get_secret_value().encode("utf-8")
    message = auth_session.token_hash.encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


async def verify_csrf(
    request: Request,
    user: Annotated[User, Depends(require_current_user)],
) -> None:
    if request.method in ("GET", "HEAD", "OPTIONS", "TRACE"):
        return

    settings = get_settings(request)
    auth_session: AuthSession | None = getattr(request.state, "auth_session", None)
    if auth_session is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geçersiz oturum.")

    token = request.headers.get("X-CSRF-Token")
    if not token:
        # Check form data if applicable
        try:
            form = await request.form()
            token = form.get("csrf_token")
        except Exception:
            token = None

    if not token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Eksik CSRF token.")

    expected = get_csrf_token_for_session(auth_session, settings)
    if not hmac.compare_digest(token, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Geçersiz CSRF token.")


def assert_user_access(
    user_id: UUID | str,
    current_user: User | None,
    settings: Settings | None = None,
) -> None:
    if current_user is None:
        if settings is None or not settings.allow_unauthenticated_legacy:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Oturum açmanız gerekiyor.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return
    if str(user_id) != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Erişim yetkiniz yok.",
        )
