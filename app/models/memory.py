from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import UTCDateTime
from app.models.user import utc_now


def new_id() -> str:
    return str(uuid4())


class Memory(Base):
    __tablename__ = 'memories'
    __table_args__ = (
        UniqueConstraint('user_id', 'id', name='uq_memories_owner'),
        ForeignKeyConstraint(
            ['user_id', 'source_message_id'],
            ['messages.user_id', 'messages.id'],
            ondelete='SET NULL',
            name='fk_memories_source_message',
        ),
        CheckConstraint("status IN ('active', 'superseded', 'deleted')", name='ck_memories_status'),
        CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='ck_memories_confidence'),
        Index('ix_memories_user_status', 'user_id', 'status'),
        Index('ix_memories_user_category', 'user_id', 'category'),
        Index('ix_memories_user_key', 'user_id', 'key'),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='active', nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now, nullable=False)
    last_confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), default=utc_now, nullable=True)
