"""Manual activity foundation; external sources can be added without changing contracts."""
from datetime import date, datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.db.types import Amount, UTCDateTime
from app.models.user import utc_now


class DailySteps(Base):
    __tablename__ = "daily_steps"
    __table_args__ = (
        UniqueConstraint("user_id", "day", "source", name="uq_steps_user_day_source"),
        CheckConstraint("step_count >= 0", name="ck_steps_nonnegative"),
        Index("ix_steps_user_day", "user_id", "day"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day: Mapped[date] = mapped_column(Date)
    step_count: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)


class Workout(Base):
    __tablename__ = "workouts"
    __table_args__ = (
        CheckConstraint("duration_minutes > 0", name="ck_workout_duration"),
        CheckConstraint("met_value IS NULL OR met_value > 0", name="ck_workout_met"),
        CheckConstraint("estimated_calories IS NULL OR estimated_calories >= 0", name="ck_workout_calories"),
        Index("ix_workouts_user_occurred", "user_id", "occurred_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime())
    activity_type: Mapped[str] = mapped_column(String(50))
    duration_minutes: Mapped[int] = mapped_column(Integer)
    intensity: Mapped[str] = mapped_column(String(20), default="moderate")
    met_value: Mapped[Decimal | None] = mapped_column(Amount())
    estimated_calories: Mapped[Decimal | None] = mapped_column(Amount())
    calorie_estimate_source: Mapped[str | None] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(30), default="manual")
    notes: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utc_now, onupdate=utc_now)
