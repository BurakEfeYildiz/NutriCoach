from datetime import date, datetime, timezone
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class UserCreate(Schema):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    timezone: str = Field(default="Europe/Istanbul", max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Geçerli bir IANA saat dilimi girin.")
        return value


class UserRead(UserCreate):
    id: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ProfileWrite(Schema):
    birth_date: date | None = None
    biological_sex: Literal["female", "male", "unspecified"] | None = None
    height_cm: float | None = Field(default=None, gt=0, le=300)
    goal_weight_kg: float | None = Field(default=None, gt=0, le=1000)
    activity_level: Literal["sedentary", "light", "moderate", "active", "very_active"] | None = None
    calorie_target: int | None = Field(default=None, gt=0, le=20000)
    protein_target_g: float | None = Field(default=None, ge=0, le=5000)
    carb_target_g: float | None = Field(default=None, ge=0, le=5000)
    fat_target_g: float | None = Field(default=None, ge=0, le=5000)
    preferred_weekly_weight_change_kg: float | None = Field(default=None, ge=-10, le=10)

    @field_validator("birth_date")
    @classmethod
    def not_future(cls, value: date | None) -> date | None:
        if value and value > datetime.now(timezone.utc).date():
            raise ValueError("Doğum tarihi gelecekte olamaz.")
        return value


class ProfileRead(ProfileWrite):
    user_id: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
