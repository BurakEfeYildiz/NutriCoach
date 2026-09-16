"""Compact deterministic Product V2 analytics contracts."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.nutrition import Totals
from app.schemas.user import Schema

Confidence = Literal["insufficient", "low", "medium", "high"]
Completeness = Literal["none", "partial", "likely_complete"]


class DayQuality(Schema):
    date: date
    status: Completeness
    meal_count: int
    distinct_main_meals: int
    has_extras: bool
    totals: Totals | None = None


class NutritionWindow(Schema):
    window_days: int
    start_date: date
    end_date: date
    logged_days: int
    usable_days: int
    missing_days: int
    average_over_usable_days: Totals | None = None
    calorie_hit_days: int | None = None
    protein_hit_days: int | None = None
    carb_within_days: int | None = None
    fat_within_days: int | None = None
    meal_averages: dict[str, Totals | None] = Field(default_factory=dict)
    meal_support_days: dict[str, int] = Field(default_factory=dict)
    extras_average_calories: Decimal | None = None


class WeightTrend(Schema):
    current_raw_weight_kg: Decimal | None = None
    current_trend_weight_kg: Decimal | None = None
    trend_weight_7d_ago_kg: Decimal | None = None
    trend_weight_14d_ago_kg: Decimal | None = None
    weekly_change_kg: Decimal | None = None
    weekly_change_percent: Decimal | None = None
    weigh_in_count: int = 0
    observation_span_days: int = 0
    latest_age_days: int | None = None
    confidence: Confidence = "insufficient"


class ActivityWindow(Schema):
    window_days: int
    step_recorded_days: int
    average_steps_over_recorded_days: Decimal | None = None
    workout_count: int
    workout_minutes: int
    estimated_workout_calories: Decimal | None = None


class ActivityAnalytics(Schema):
    steps_today: int | None = None
    steps_vs_7d_average: Decimal | None = None
    days_7: ActivityWindow
    days_14: ActivityWindow


class ExpenditureEstimate(Schema):
    estimated_expenditure_kcal: Decimal | None = None
    source: Literal["initial_estimate", "adaptive_estimate", "unavailable"]
    confidence: Confidence
    initial_estimate_kcal: Decimal | None = None
    usable_overlap_days: int = 0
    observation_days: int = 0
    method: str = "conservative_weight_energy_v1"


class GoalProgress(Schema):
    status: str | None = None
    current_weight_kg: Decimal | None = None
    trend_weight_kg: Decimal | None = None
    target_weight_kg: Decimal | None = None
    remaining_weight_kg: Decimal | None = None
    planned_rate_percent_per_week: Decimal | None = None
    actual_rate_percent_per_week: Decimal | None = None
    planned_eta_earliest: date | None = None
    planned_eta_latest: date | None = None
    trend_eta_earliest: date | None = None
    trend_eta_latest: date | None = None


class PatternSignal(Schema):
    key: str
    status: str
    magnitude: Decimal | None = None
    supporting_days: int
    window_days: int
    confidence: Confidence


class InsightCandidate(Schema):
    type: str
    priority: int
    confidence: Confidence
    facts: dict[str, Decimal | int | str | None]
    text: str


class TargetSuggestion(Schema):
    action: Literal["keep_current_target", "consider_small_increase", "consider_small_decrease", "insufficient_data"]
    proposed_delta_kcal: int = 0
    reason: str
    automatically_applied: bool = False


class WeeklyReview(Schema):
    start_date: date
    end_date: date
    nutrition: NutritionWindow
    weight: WeightTrend
    activity: ActivityWindow
    expenditure: ExpenditureEstimate
    goal: GoalProgress
    patterns: list[PatternSignal] = Field(default_factory=list)
    target_suggestion: TargetSuggestion
    interpretation_prompt: str


class Gamification(Schema):
    current_logging_streak: int
    longest_logging_streak_14d: int
    logging_consistency_14d_percent: Decimal
    likely_complete_days_14d: int
    achievements: list[str] = Field(default_factory=list)


class AdaptiveDashboard(Schema):
    date: date
    timezone: str
    today_quality: DayQuality
    nutrition_7d: NutritionWindow
    nutrition_14d: NutritionWindow
    weight: WeightTrend
    activity: ActivityAnalytics
    expenditure: ExpenditureEstimate
    goal: GoalProgress
    patterns: list[PatternSignal]
    insights: list[InsightCandidate]
    gamification: Gamification
    weekly_review: WeeklyReview
