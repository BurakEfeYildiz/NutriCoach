from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.nutrition import Totals
from app.schemas.analytics import ActivityAnalytics, DayQuality, ExpenditureEstimate, GoalProgress, InsightCandidate, NutritionWindow, PatternSignal, WeightTrend, WeeklyReview
from app.schemas.user import Schema


class ProfileContext(Schema):
    birth_date: date | None = None
    age: int | None = None
    biological_sex: str | None = None
    height_cm: float | None = None
    current_weight_kg: Decimal | None = None
    goal_weight_kg: float | None = None
    preferred_weekly_weight_change_kg: float | None = None
    activity_level: str | None = None
    goal_type: str | None = None
    training_frequency: str | None = None
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
    calories_consumed: Decimal | None = None
    protein_consumed_g: Decimal | None = None
    carbohydrate_consumed_g: Decimal | None = None
    fat_consumed_g: Decimal | None = None
    remaining_by_target: dict[str, Decimal | None] = Field(default_factory=dict)
    remaining_calories: Decimal | None = None
    remaining_protein_g: Decimal | None = None
    remaining_carbohydrate_g: Decimal | None = None
    remaining_fat_g: Decimal | None = None
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


class PlanContext(Schema):
    status: str | None = None
    constraint_reason: str | None = None
    current_weight_kg: Decimal | None = None
    bmr_kcal: int | None = None
    estimated_expenditure_kcal: int | None = None
    expenditure_source: str | None = None
    calorie_target: int | None = None
    protein_target_g: Decimal | None = None
    carbohydrate_target_g: Decimal | None = None
    fat_target_g: Decimal | None = None
    planned_rate_percent_per_week: Decimal | None = None
    planned_rate_kg_per_week: Decimal | None = None
    planned_eta_earliest: date | None = None
    planned_eta_latest: date | None = None
    eta_source: str | None = None
    calculation_version: str | None = None


class ActivityWorkoutContext(Schema):
    activity_type: str
    duration_minutes: int
    intensity: str
    estimated_calories: Decimal | None = None
    calorie_estimate_source: str | None = None


class ActivityContext(Schema):
    date: date
    has_step_records: bool
    total_steps: int | None = None
    total_workout_minutes: int = 0
    estimated_activity_calories: Decimal | None = None
    workouts: list[ActivityWorkoutContext] = Field(default_factory=list)


class RecipeSuggestionContext(Schema):
    name: str
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    why_it_fits: str | None = None
    nutrition_status: str


class AdaptiveContext(Schema):
    today_logging: DayQuality
    weight_trend: WeightTrend
    expenditure: ExpenditureEstimate
    goal_progress: GoalProgress
    nutrition_7d: NutritionWindow
    nutrition_14d: NutritionWindow | None = None
    activity: ActivityAnalytics | None = None
    pattern_signals: list[PatternSignal] = Field(default_factory=list)
    daily_insights: list[InsightCandidate] = Field(default_factory=list)
    weekly_review: WeeklyReview | None = None
    recipe_suggestions: list[RecipeSuggestionContext] = Field(default_factory=list)


class CoachContext(Schema):
    generated_at: datetime
    timezone: str
    local_date: date
    categories: list[str] = Field(default_factory=list)
    included_sections: list[str] = Field(default_factory=list)
    profile: ProfileContext | None = None
    plan: PlanContext | None = None
    today: TodayContext | None = None
    yesterday: YesterdayContext | None = None
    recent_7_days: PeriodSummaryContext | None = None
    recent_14_days: PeriodSummaryContext | None = None
    weight: WeightContext | None = None
    activity: ActivityContext | None = None
    adaptive: AdaptiveContext | None = None
    memories: list[MemoryContext] = Field(default_factory=list)
    memory_count_available: int = 0
    memory_detail_truncated: bool = False
    recent_messages: list[RecentChatMessageContext] = Field(default_factory=list)
