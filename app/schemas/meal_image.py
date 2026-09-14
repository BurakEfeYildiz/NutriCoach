from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.schemas.nutrition import Nonnegative, Positive
from app.schemas.user import Schema


class MealImageItem(Schema):
    name: str = Field(min_length=1, max_length=200, description="Yiyecek veya içecek adı")
    quantity: Positive = Field(description="Tahmini porsiyon miktarı")
    unit: str = Field(min_length=1, max_length=30, description="Birim (g, porsiyon, dilim, kase, adet vb.)")
    calories: Nonnegative = Field(description="Tahmini toplam kalori")
    protein_g: Nonnegative = Field(description="Tahmini protein (g)")
    carbs_g: Nonnegative = Field(description="Tahmini karbonhidrat (g)")
    fat_g: Nonnegative = Field(description="Tahmini yağ (g)")


class MealImageAnalysisResult(Schema):
    meal_type: Literal['breakfast', 'lunch', 'dinner', 'snack'] = 'lunch'
    items: list[MealImageItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confidence: Decimal | None = Field(default=None, ge=0, le=1, max_digits=3, decimal_places=2)
