from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from app.schemas.user import Schema

Nonnegative = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=12, decimal_places=2)]
Positive = Annotated[Decimal, Field(gt=0, le=1000000, max_digits=12, decimal_places=2)]
Source = Literal['manual', 'label', 'estimate', 'user_corrected', 'usda', 'open_food_facts', 'user', 'structured', 'ai_estimate', 'photo_estimate']


class ItemWrite(Schema):
    name: str = Field(min_length=1, max_length=200)
    quantity: Positive
    unit: str = Field(min_length=1, max_length=30)
    # These values describe the entire item portion, never per 100 g.
    calories: Nonnegative
    protein_g: Nonnegative
    carbs_g: Nonnegative
    fat_g: Nonnegative
    source: Source = 'manual'
    assumptions: str | None = Field(default=None, max_length=2000)


class ItemRead(ItemWrite):
    id: str
    user_id: str
    meal_id: str
    food_id: str | None = None
    food_portion_id: str | None = None
    food_source: str | None = None
    source_food_id: str | None = None
    portion_label: str | None = None


class MealWrite(Schema):
    occurred_at: AwareDatetime
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack', 'extra', 'other'] = 'other'
    original_description: str = Field(min_length=1, max_length=4000)
    normalized_description: str | None = Field(default=None, max_length=4000)
    nutrition_source: Source = 'manual'
    confidence: Decimal | None = Field(default=None, ge=0, le=1, max_digits=3, decimal_places=2)
    items: list[ItemWrite] = Field(min_length=1, max_length=100)


class MealReplace(MealWrite):
    expected_version: int = Field(gt=0)


class Totals(Schema):
    calories: Decimal = Decimal('0.00')
    protein_g: Decimal = Decimal('0.00')
    carbs_g: Decimal = Decimal('0.00')
    fat_g: Decimal = Decimal('0.00')


class MealRead(MealWrite):
    id: str
    user_id: str
    version: int
    created_at: datetime
    updated_at: datetime
    items: list[ItemRead]
    totals: Totals


class DaySummary(Schema):
    date: date
    timezone: str
    meal_count: int
    has_records: bool
    totals: Totals | None
    # Targets may be individually unknown.
    remaining_by_target: dict[str, Decimal | None]


class WeekSummary(Schema):
    start_date: date
    end_date: date
    timezone: str
    recorded_days: int
    missing_days: int
    average_over_recorded_days: Totals | None
    days_above_current_calorie_target: int | None
    days_below_current_calorie_target: int | None
    days: list[DaySummary]


class WeightWrite(Schema):
    occurred_at: AwareDatetime
    weight_kg: Decimal = Field(gt=0, le=1000, max_digits=6, decimal_places=2)


class WeightRead(WeightWrite):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
