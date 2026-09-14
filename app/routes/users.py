from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.user import User
from app.routes.dependencies import SettingsDep, assert_user_access, get_current_user_optional, get_session
from app.schemas.user import ProfileRead, ProfileWrite, UserCreate, UserRead
from app.services import users

router = APIRouter(prefix="/users", tags=["users (local development)"])
Database = Annotated[Session, Depends(get_session)]
CurrentUserOpt = Annotated[User | None, Depends(get_current_user_optional)]


@router.post("", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, session: Database):
    return users.create_user(session, data)


@router.get("", response_model=list[UserRead])
def list_users(session: Database, limit: int = 50):
    from sqlalchemy import select
    return list(session.scalars(select(User).order_by(User.created_at.desc()).limit(limit)))


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, session: Database, settings: SettingsDep, current_user: CurrentUserOpt = None):
    assert_user_access(user_id, current_user, settings)
    return users.get_user(session, str(user_id))


@router.get("/{user_id}/profile", response_model=ProfileRead)
def get_profile(user_id: UUID, session: Database, settings: SettingsDep, current_user: CurrentUserOpt = None):
    assert_user_access(user_id, current_user, settings)
    return users.get_user(session, str(user_id)).profile


@router.put("/{user_id}/profile", response_model=ProfileRead)
def replace_profile(user_id: UUID, data: ProfileWrite, session: Database, settings: SettingsDep, current_user: CurrentUserOpt = None):
    """Profilin tamamını değiştirir; gönderilmeyen alanlar temizlenir."""
    assert_user_access(user_id, current_user, settings)
    return users.replace_profile(session, str(user_id), data)
