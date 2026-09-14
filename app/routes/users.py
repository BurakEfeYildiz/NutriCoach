from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.routes.dependencies import get_session
from app.schemas.user import ProfileRead, ProfileWrite, UserCreate, UserRead
from app.services import users

router = APIRouter(prefix="/users", tags=["users (local development)"])
Database = Annotated[Session, Depends(get_session)]


@router.post("", response_model=UserRead, status_code=201)
def create_user(data: UserCreate, session: Database):
    return users.create_user(session, data)


@router.get("/{user_id}", response_model=UserRead)
def get_user(user_id: UUID, session: Database):
    return users.get_user(session, str(user_id))


@router.get("/{user_id}/profile", response_model=ProfileRead)
def get_profile(user_id: UUID, session: Database):
    return users.get_user(session, str(user_id)).profile


@router.put("/{user_id}/profile", response_model=ProfileRead)
def replace_profile(user_id: UUID, data: ProfileWrite, session: Database):
    """Profilin tamamını değiştirir; gönderilmeyen alanlar temizlenir."""
    return users.replace_profile(session, str(user_id), data)
