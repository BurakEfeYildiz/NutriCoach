from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import UTCDateTime
from app.models.nutrition import new_id
from app.models.user import utc_now


class Conversation(Base):
    __tablename__ = 'conversations'
    __table_args__ = (
        UniqueConstraint('user_id', 'id', name='uq_conversations_owner'),
        Index('ix_conversations_user_created', 'user_id', 'created_at'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'conversation_id'], ['conversations.user_id', 'conversations.id'], ondelete='CASCADE', name='fk_messages_conversation_owner'),
        UniqueConstraint('user_id', 'id', name='uq_messages_owner'),
        UniqueConstraint('user_id', 'conversation_id', 'id', name='uq_messages_conversation_owner'),
        ForeignKeyConstraint(['user_id', 'conversation_id', 'in_reply_to'], ['messages.user_id', 'messages.conversation_id', 'messages.id'], name='fk_messages_reply_owner'),
        UniqueConstraint('user_id', 'client_request_id', name='uq_messages_client_request'),
        UniqueConstraint('in_reply_to', name='uq_messages_one_reply'),
        Index('ix_messages_user_conversation_created', 'user_id', 'conversation_id', 'created_at'),
        CheckConstraint("role IN ('user', 'assistant')", name='ck_messages_role'),
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name='ck_messages_status'),
        CheckConstraint("(role = 'user' AND client_request_id IS NOT NULL AND in_reply_to IS NULL) OR (role = 'assistant' AND client_request_id IS NULL AND in_reply_to IS NOT NULL)", name='ck_messages_role_keys'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36))
    conversation_id: Mapped[str] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    client_request_id: Mapped[str | None] = mapped_column(String(36))
    in_reply_to: Mapped[str | None] = mapped_column(String(36))
    effects_committed: Mapped[bool] = mapped_column(Boolean, default=False)
    action_results: Mapped[list] = mapped_column(JSON, default=list)
    error_type: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)


class AIRequest(Base):
    __tablename__ = 'ai_requests'
    __table_args__ = (
        ForeignKeyConstraint(['user_id', 'message_id'], ['messages.user_id', 'messages.id'], ondelete='CASCADE', name='fk_ai_requests_message_owner'),
        Index('ix_ai_requests_user_created', 'user_id', 'created_at'),
        CheckConstraint("status IN ('pending', 'completed', 'failed')", name='ck_ai_requests_status'),
        CheckConstraint("phase IN ('intent', 'coach')", name='ck_ai_requests_phase'),
        *(CheckConstraint(f'{field} IS NULL OR {field} >= 0', name=f'ck_ai_requests_{field}') for field in ('input_tokens', 'output_tokens', 'total_tokens', 'latency_ms')),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(String(36))
    message_id: Mapped[str] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(200))
    phase: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='pending')
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    total_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    error_type: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
