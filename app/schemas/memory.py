from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.user import Schema

MemoryCategory = Literal[
    'food_preference',
    'food_dislike',
    'dietary_habit',
    'exercise_routine',
    'schedule_routine',
    'practical_constraint',
    'coaching_preference',
    'lifestyle',
]


class MemoryCandidate(Schema):
    category: MemoryCategory
    key: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=500)
    confidence: Decimal = Field(default=Decimal('0.80'), ge=0, le=1)
    evidence: str = Field(default='', max_length=500)


class MemoryExtractionResult(Schema):
    candidates: list[MemoryCandidate] = Field(default_factory=list, max_length=3)


class MemoryRead(Schema):
    id: str
    user_id: str
    category: str
    key: str
    value: str
    status: str
    confidence: Decimal | None = None
    source_message_id: str | None = None
    created_at: datetime
    updated_at: datetime
    last_confirmed_at: datetime | None = None
