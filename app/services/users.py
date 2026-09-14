from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user import User, UserProfile
from app.schemas.user import ProfileWrite, UserCreate


def get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    return user


def create_user(session: Session, data: UserCreate) -> User:
    values = data.model_dump()
    if values["email"]:
        values["email"] = values["email"].lower()
    user = User(**values, profile=UserProfile())
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bu e-posta zaten kayıtlı.")
    return user


def replace_profile(session: Session, user_id: str, data: ProfileWrite, *, commit: bool = True) -> UserProfile:
    profile = get_user(session, user_id).profile
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    session.commit() if commit else session.flush()
    return profile
