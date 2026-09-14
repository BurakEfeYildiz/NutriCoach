from datetime import datetime, timedelta, timezone
import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import AuthSession
from app.models.user import User, UserProfile
from app.schemas.auth import RegisterRequest

_hasher = PasswordHasher()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> tuple[bool, bool]:
    if not password_hash:
        return False, False
    try:
        is_valid = _hasher.verify(password_hash, password)
        needs_rehash = _hasher.check_needs_rehash(password_hash)
        return is_valid, needs_rehash
    except (VerifyMismatchError, InvalidHashError):
        return False, False


def register_user(session: Session, data: RegisterRequest) -> User:
    email_normalized = data.email.strip().lower()
    existing = session.scalar(select(User).where(User.email == email_normalized))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta adresi ile kayıtlı bir hesap zaten var.",
        )

    pwd_hash = hash_password(data.password)
    user = User(
        name=data.name.strip(),
        email=email_normalized,
        password_hash=pwd_hash,
        timezone=data.timezone,
        profile=UserProfile(),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Bu e-posta adresi ile kayıtlı bir hesap zaten var.",
        )
    session.refresh(user)
    return user


def authenticate_user(session: Session, email: str, password: str) -> User:
    generic_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email veya şifre hatalı.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    email_normalized = email.strip().lower()
    user = session.scalar(select(User).where(User.email == email_normalized))
    if user is None or not user.password_hash:
        raise generic_error

    valid, needs_rehash = verify_password(password, user.password_hash)
    if not valid:
        raise generic_error

    if needs_rehash:
        user.password_hash = hash_password(password)
        session.commit()

    return user


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_session(session: Session, user_id: str, ttl_days: int = 30) -> tuple[AuthSession, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    expires_at = utc_now() + timedelta(days=ttl_days)

    auth_session = AuthSession(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
        created_at=utc_now(),
        last_seen_at=utc_now(),
    )
    session.add(auth_session)
    session.commit()
    session.refresh(auth_session)
    return auth_session, raw_token


def validate_session_token(session: Session, raw_token: str) -> tuple[AuthSession, User] | None:
    if not raw_token:
        return None
    token_hash = hash_token(raw_token)
    stmt = (
        select(AuthSession)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utc_now(),
        )
    )
    auth_session = session.scalar(stmt)
    if auth_session is None:
        return None

    # Load user
    user = session.get(User, auth_session.user_id)
    if user is None:
        return None

    # Throttle last_seen_at writes to at most once every 5 minutes (300 seconds)
    if (utc_now() - auth_session.last_seen_at.replace(tzinfo=timezone.utc)).total_seconds() > 300:
        auth_session.last_seen_at = utc_now()
        session.commit()

    return auth_session, user


def revoke_session(session: Session, raw_token: str) -> None:
    if not raw_token:
        return
    token_hash = hash_token(raw_token)
    stmt = select(AuthSession).where(AuthSession.token_hash == token_hash, AuthSession.revoked_at.is_(None))
    auth_session = session.scalar(stmt)
    if auth_session:
        auth_session.revoked_at = utc_now()
        session.commit()


def revoke_all_user_sessions(session: Session, user_id: str, except_token_hash: str | None = None) -> None:
    stmt = select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_token_hash:
        stmt = stmt.where(AuthSession.token_hash != except_token_hash)
    sessions = session.scalars(stmt).all()
    for s in sessions:
        s.revoked_at = utc_now()
    session.commit()


def change_user_password(
    session: Session,
    user: User,
    current_password: str,
    new_password: str,
    current_raw_token: str | None = None,
) -> None:
    if user.password_hash:
        valid, _ = verify_password(current_password, user.password_hash)
        if not valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mevcut şifre hatalı.",
            )

    user.password_hash = hash_password(new_password)
    user.updated_at = utc_now()

    current_token_hash = hash_token(current_raw_token) if current_raw_token else None
    revoke_all_user_sessions(session, user.id, except_token_hash=current_token_hash)
    session.commit()


def set_user_password_cli(session: Session, identifier: str, new_password: str) -> User:
    """CLI / dev helper to assign credentials to existing development or legacy users."""
    user = session.get(User, identifier)
    if user is None:
        user = session.scalar(select(User).where(User.email == identifier.strip().lower()))
    if user is None:
        raise ValueError(f"Kullanıcı bulunamadı: {identifier}")

    user.password_hash = hash_password(new_password)
    user.updated_at = utc_now()
    revoke_all_user_sessions(session, user.id)
    session.commit()
    session.refresh(user)
    return user
