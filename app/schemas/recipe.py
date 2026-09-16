from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from app.schemas.nutrition import Totals
from app.schemas.user import Schema


class RecipeIngredientWrite(Schema):
    food_id: str | None = None
    portion_id: str | None = None
    quantity: Decimal = Field(gt=0, le=100000, max_digits=12, decimal_places=2)
    unit: str = Field(min_length=1, max_length=40)
    fallback_text: str | None = Field(default=None, max_length=200)
    allergen_tags: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def has_source(self):
        if not self.food_id and not self.fallback_text:
            raise ValueError("Yapılandırılmış yiyecek veya açıkça belirtilmiş tahmini malzeme gerekli.")
        return self


class RecipeCreate(Schema):
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=800)
    servings: int = Field(gt=0, le=100)
    instructions: list[str] = Field(min_length=1, max_length=30)
    tags: list[str] = Field(default_factory=list, max_length=20)
    ingredients: list[RecipeIngredientWrite] = Field(min_length=1, max_length=30)


class RecipeIngredientRead(RecipeIngredientWrite):
    id: str
    name: str
    provenance: str
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None


class RecipeRead(Schema):
    id: str
    name: str
    description: str
    servings: int
    instructions: list[str]
    tags: list[str]
    source: Literal["curated", "user", "ai_generated"]
    nutrition_status: Literal["structured", "partial"]
    per_serving: Totals | None
    ingredients: list[RecipeIngredientRead]
    why_it_fits: str | None = None


class DietaryExclusions(Schema):
    foods: list[str] = Field(default_factory=list, max_length=30)
