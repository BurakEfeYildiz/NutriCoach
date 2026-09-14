from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.nutrition import Totals
from app.schemas.user import Schema


class ProfileContext(Schema):
    birth_date: date | None = None
    age: int | None = None
    biological_sex: str | None = None
    height_cm: float | None = None
    goal_weight_kg: float | None = None
    preferred_weekly_weight_change_kg: float | None = None
    activity_level: str | None = None
    calorie_target: int | None = None
    protein_target_g: float | None = None
    carb_target_g: float | None = None
    fat_target_g: float | None = None
    timezone: str


class ItemContext(Schema):
    name: str
    quantity: Decimal
    unit: str
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    source: str
    assumptions: str | None = None


class MealContext(Schema):
    meal_type: str
    occurred_at: str
    original_description: str
    nutrition_source: str
    confidence: Decimal | None = None
    totals: Totals
    items: list[ItemContext] = Field(default_factory=list)


class TodayContext(Schema):
    date: date
    has_records: bool
    meal_count: int
    totals: Totals | None = None
    remaining_by_target: dict[str, Decimal | None] = Field(default_factory=dict)
    meals: list[MealContext] = Field(default_factory=list)
    detail_truncated: bool = False


class YesterdayContext(Schema):
    date: date
    has_records: bool
    meal_count: int
    totals: Totals | None = None


class PeriodSummaryContext(Schema):
    start_date: date
    end_date: date
    days_count: int
    recorded_days: int
    missing_days: int
    average_over_recorded_days: Totals | None = None
    min_calories_over_recorded_days: Decimal | None = None
    max_calories_over_recorded_days: Decimal | None = None
    days_above_current_calorie_target: int | None = None
    days_below_current_calorie_target: int | None = None


class WeightPointContext(Schema):
    date: date
    occurred_at: datetime
    weight_kg: Decimal


class WeightContext(Schema):
    current_weight_kg: Decimal | None = None
    current_weight_date: date | None = None
    measurement_count: int = 0
    trend: Literal['insufficient_data', 'stable', 'increasing', 'decreasing'] = 'insufficient_data'
    delta_kg: Decimal | None = None
    rate_kg_per_week: Decimal | None = None
    history: list[WeightPointContext] = Field(default_factory=list)
    detail_truncated: bool = False


class RecentChatMessageContext(Schema):
    role: str
    content: str


class MemoryContext(Schema):
    category: str
    key: str
    value: str
    confidence: Decimal | None = None


class CoachContext(Schema):
    generated_at: datetime
    timezone: str
    local_date: date
    categories: list[str] = Field(default_factory=list)
    included_sections: list[str] = Field(default_factory=list)
    profile: ProfileContext | None = None
    today: TodayContext | None = None
    yesterday: YesterdayContext | None = None
    recent_7_days: PeriodSummaryContext | None = None
    recent_14_days: PeriodSummaryContext | None = None
    weight: WeightContext | None = None
    memories: list[MemoryContext] = Field(default_factory=list)
    memory_count_available: int = 0
    memory_detail_truncated: bool = False
    recent_messages: list[RecentChatMessageContext] = Field(default_factory=list)
