from sqlalchemy import select
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.nutrition import WeightLog
from app.schemas.nutrition import WeightWrite
from app.services.users import get_user


def owned_weight(session: Session, user_id: str, weight_id: str) -> WeightLog:
    weight = session.scalar(select(WeightLog).where(WeightLog.user_id == user_id, WeightLog.id == weight_id))
    if weight is None:
        raise HTTPException(404, 'Kilo kaydı bulunamadı.')
    return weight


def list_weights(session: Session, user_id: str, limit: int = 100, offset: int = 0) -> list[WeightLog]:
    get_user(session, user_id)
    return list(session.scalars(select(WeightLog).where(WeightLog.user_id == user_id).order_by(
        WeightLog.occurred_at.desc(), WeightLog.created_at.desc(), WeightLog.id.desc()
    ).limit(limit).offset(offset)))


def current_weight(session: Session, user_id: str) -> WeightLog | None:
    rows = list_weights(session, user_id, limit=1)
    return rows[0] if rows else None


def create_weight(session: Session, user_id: str, data: WeightWrite, *, commit: bool = True) -> WeightLog:
    get_user(session, user_id)
    weight = WeightLog(user_id=user_id, **data.model_dump())
    session.add(weight)
    session.commit() if commit else session.flush()
    session.refresh(weight)
    return weight


def replace_weight(session: Session, user_id: str, weight_id: str, data: WeightWrite) -> WeightLog:
    weight = owned_weight(session, user_id, weight_id)
    for key, value in data.model_dump().items():
        setattr(weight, key, value)
    session.commit()
    session.refresh(weight)
    return weight


def delete_weight(session: Session, user_id: str, weight_id: str) -> None:
    session.delete(owned_weight(session, user_id, weight_id))
    session.commit()
