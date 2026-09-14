from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.user import Schema


class ConversationRead(Schema):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(Schema):
    client_request_id: UUID
    content: str = Field(min_length=1, max_length=4000)


class ActionResult(Schema):
    type: str
    record_id: str
    version: int | None = None


class MessageRead(Schema):
    id: str
    user_id: str
    conversation_id: str
    role: Literal['user', 'assistant']
    content: str
    status: Literal['pending', 'completed', 'failed']
    client_request_id: str | None
    in_reply_to: str | None
    effects_committed: bool
    action_results: list[ActionResult]
    error_type: str | None
    created_at: datetime


class MessageResult(Schema):
    user_message: MessageRead
    assistant_message: MessageRead | None
