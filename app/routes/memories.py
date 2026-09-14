from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.routes.dependencies import get_session
from app.schemas.memory import MemoryRead
from app.services.memory_service import deactivate_memory
from app.services.users import get_user

router = APIRouter(prefix="/users/{user_id}/memories", tags=["memories"])
Database = Annotated[Session, Depends(get_session)]


@router.get("", response_model=list[MemoryRead])
def list_memories(
    user_id: UUID,
    session: Database,
    include_inactive: bool = False,
    limit: int = 100,
):
    get_user(session, str(user_id))
    query = select(Memory).where(Memory.user_id == str(user_id))
    if not include_inactive:
        query = query.where(Memory.status == 'active')
    query = query.order_by(Memory.last_confirmed_at.desc(), Memory.created_at.desc()).limit(limit)
    rows = list(session.scalars(query))
    return [MemoryRead.model_validate(row) for row in rows]


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(user_id: UUID, memory_id: UUID, session: Database):
    get_user(session, str(user_id))
    success = deactivate_memory(session, str(user_id), str(memory_id))
    if not success:
        raise HTTPException(status_code=404, detail="Hafıza kaydı bulunamadı.")
    session.commit()
