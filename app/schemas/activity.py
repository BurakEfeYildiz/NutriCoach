from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field

from app.schemas.user import Schema


class DailyStepsWrite(Schema):
    day: date
    step_count: int = Field(ge=0, le=500000)
    source: Literal["manual", "apple_health"] = "manual"


class DailyStepsRead(DailyStepsWrite):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class WorkoutWrite(Schema):
    occurred_at: AwareDatetime
    activity_type: Literal["walking", "running", "cycling", "strength", "swimming", "yoga", "other"]
    duration_minutes: int = Field(gt=0, le=1440)
    intensity: Literal["light", "moderate", "vigorous"] = "moderate"
    source: Literal["manual", "apple_health"] = "manual"
    notes: str | None = Field(default=None, max_length=500)


class WorkoutRead(WorkoutWrite):
    id: str
    user_id: str
    met_value: Decimal | None
    estimated_calories: Decimal | None
    calorie_estimate_source: str | None
    created_at: datetime
    updated_at: datetime


class ActivityToday(Schema):
    date: date
    timezone: str
    steps: list[DailyStepsRead]
    total_steps: int | None
    workouts: list[WorkoutRead]
    total_workout_minutes: int
    estimated_activity_calories: Decimal | None
