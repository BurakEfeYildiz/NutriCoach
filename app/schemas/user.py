from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

BiologicalSex = Literal["female", "male", "unspecified"]
GoalType = Literal["lose", "maintain", "gain"]
ActivityLevel = Literal["sedentary", "light", "moderate", "active", "very_active"]
TrainingFrequency = Literal["none", "one_two", "three_four", "five_plus"]


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
    goal_type: GoalType | None = None
    training_frequency: TrainingFrequency | None = None
    pace_percent_per_week: float | None = Field(default=None, ge=0, le=0.75)
    pregnancy_or_breastfeeding: bool | None = None

    @field_validator("birth_date")
    @classmethod
    def not_future(cls, value: date | None) -> date | None:
        if value and value > datetime.now(timezone.utc).date():
            raise ValueError("Doğum tarihi gelecekte olamaz.")
        return value


class ProfileRead(ProfileWrite):
    user_id: str
    onboarding_completed_at: datetime | None = None
    bmr_kcal: int | None = None
    estimated_expenditure_kcal: int | None = None
    expenditure_source: str | None = None
    planned_rate_kg_per_week: float | None = None
    planned_eta_earliest: date | None = None
    planned_eta_latest: date | None = None
    eta_source: str | None = None
    plan_status: str | None = None
    plan_constraint_reason: str | None = None
    calculation_version: str | None = None
    targets_recalculated_at: datetime | None = None
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def utc_timestamp(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class AccountUpdate(Schema):
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    timezone: str = Field(max_length=64)

    _valid_timezone = field_validator("timezone")(UserCreate.valid_timezone.__func__)


class OnboardingComplete(Schema):
    birth_date: date
    biological_sex: Literal["female", "male"]
    height_cm: Decimal = Field(ge=100, le=250, max_digits=5, decimal_places=1)
    current_weight_kg: Decimal = Field(ge=25, le=400, max_digits=5, decimal_places=2)
    target_weight_kg: Decimal = Field(ge=25, le=400, max_digits=5, decimal_places=2)
    goal_type: GoalType
    activity_level: ActivityLevel
    training_frequency: TrainingFrequency
    pace_percent_per_week: Decimal = Field(ge=0, le=0.75, max_digits=3, decimal_places=2)
    pregnancy_or_breastfeeding: bool

    @field_validator("birth_date")
    @classmethod
    def valid_birth_date(cls, value: date) -> date:
        if value > datetime.now(timezone.utc).date():
            raise ValueError("Doğum tarihi gelecekte olamaz.")
        return value


class NutritionProfileUpdate(Schema):
    birth_date: date
    biological_sex: Literal["female", "male"]
    height_cm: Decimal = Field(ge=100, le=250, max_digits=5, decimal_places=1)
    target_weight_kg: Decimal = Field(ge=25, le=400, max_digits=5, decimal_places=2)
    goal_type: GoalType
    activity_level: ActivityLevel
    training_frequency: TrainingFrequency
    pace_percent_per_week: Decimal = Field(ge=0, le=0.75, max_digits=3, decimal_places=2)
    pregnancy_or_breastfeeding: bool

    _valid_birth_date = field_validator("birth_date")(OnboardingComplete.valid_birth_date.__func__)


class NutritionPlanRead(Schema):
    onboarding_complete: bool
    missing_fields: list[str]
    current_weight_kg: Decimal | None = None
    age: int | None = None
    status: str | None = None
    constraint_reason: str | None = None
    bmr_kcal: int | None = None
    estimated_expenditure_kcal: int | None = None
    expenditure_source: str | None = None
    daily_calorie_target: int | None = None
    protein_target_g: Decimal | None = None
    carbohydrate_target_g: Decimal | None = None
    fat_target_g: Decimal | None = None
    planned_rate_percent_per_week: Decimal | None = None
    planned_rate_kg_per_week: Decimal | None = None
    planned_eta_earliest: date | None = None
    planned_eta_latest: date | None = None
    eta_source: str | None = None
    calculation_version: str | None = None
    recalculated_at: datetime | None = None


class OnboardingStatusRead(Schema):
    completed: bool
    missing_fields: list[str]
    plan: NutritionPlanRead
