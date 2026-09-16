from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.user import Schema

Nonnegative = Annotated[Decimal, Field(ge=0, le=1000000, max_digits=12, decimal_places=2)]
Positive = Annotated[Decimal, Field(gt=0, le=1000000, max_digits=12, decimal_places=2)]
Basis = Literal["per_100g", "per_100ml", "per_serving"]


class PortionRead(Schema):
    id: str
    label: str
    amount: Decimal
    unit: str
    gram_equivalent: Decimal | None
    ml_equivalent: Decimal | None
    serving_equivalent: Decimal | None
    source: str


class FoodRead(Schema):
    id: str
    owner_user_id: str | None
    canonical_name: str
    brand: str | None
    source: str
    source_food_id: str
    source_data_type: str | None
    category: str | None
    barcode: str | None
    country: str | None
    basis_type: Basis
    basis_amount: Decimal
    basis_unit: str
    calories: Decimal | None
    protein_g: Decimal | None
    carbs_g: Decimal | None
    fat_g: Decimal | None
    fiber_g: Decimal | None
    sugar_g: Decimal | None
    sodium_mg: Decimal | None
    reliability: str
    last_synced_at: datetime
    portions: list[PortionRead] = []


class FoodSearchResponse(Schema):
    local: list[FoodRead]
    external: list["ExternalFoodCandidate"]


class ExternalFoodCandidate(Schema):
    source: Literal["open_food_facts"]
    source_food_id: str
    canonical_name: str
    brand: str | None = None
    barcode: str
    country: str | None = None
    basis_type: Basis = "per_100g"
    calories: Decimal | None = None
    protein_g: Decimal | None = None
    carbs_g: Decimal | None = None
    fat_g: Decimal | None = None
    has_complete_nutrition: bool


class CustomPortionWrite(Schema):
    label: str = Field(min_length=1, max_length=120)
    amount: Positive = Decimal("1.00")
    unit: str = Field(min_length=1, max_length=40)
    gram_equivalent: Positive | None = None
    ml_equivalent: Positive | None = None
    serving_equivalent: Positive | None = None

    @model_validator(mode="after")
    def has_equivalent(self):
        if self.gram_equivalent is None and self.ml_equivalent is None and self.serving_equivalent is None:
            raise ValueError("Porsiyon için açık bir gram, ml veya servis karşılığı gerekli.")
        return self


class CustomFoodCreate(Schema):
    canonical_name: str = Field(min_length=1, max_length=240)
    brand: str | None = Field(default=None, max_length=160)
    basis_type: Basis
    basis_amount: Positive
    basis_unit: Literal["g", "ml", "serving"]
    calories: Nonnegative
    protein_g: Nonnegative
    carbs_g: Nonnegative
    fat_g: Nonnegative
    fiber_g: Nonnegative | None = None
    sugar_g: Nonnegative | None = None
    sodium_mg: Nonnegative | None = None
    aliases: list[str] = Field(default_factory=list, max_length=20)
    portions: list[CustomPortionWrite] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def basis_is_coherent(self):
        expected = {"per_100g": (Decimal("100"), "g"), "per_100ml": (Decimal("100"), "ml")}
        if self.basis_type in expected and (self.basis_amount, self.basis_unit) != expected[self.basis_type]:
            raise ValueError("100 g/ml temeli, karşılık gelen 100 miktarı ve birimiyle kaydedilmelidir.")
        if self.basis_type == "per_serving" and self.basis_unit != "serving":
            raise ValueError("Servis temelli yiyeceğin birimi serving olmalıdır.")
        return self


class FoodLogPreviewRequest(Schema):
    food_id: str
    quantity: Positive
    portion_id: str | None = None
    unit: Literal["g", "ml", "serving"] | None = None

    @model_validator(mode="after")
    def one_measure(self):
        if bool(self.portion_id) == bool(self.unit):
            raise ValueError("Porsiyon veya açık birimden yalnızca biri seçilmelidir.")
        return self


class FoodLogPreview(Schema):
    food_id: str
    food_name: str
    quantity: Decimal
    unit: str
    portion_id: str | None
    portion_label: str | None
    calories: Decimal
    protein_g: Decimal
    carbs_g: Decimal
    fat_g: Decimal
    fiber_g: Decimal | None
    sugar_g: Decimal | None
    sodium_mg: Decimal | None
    source: str
    reliability: str


class FoodLogCreate(FoodLogPreviewRequest):
    occurred_at: AwareDatetime
    meal_type: Literal["breakfast", "lunch", "dinner", "snack", "extra", "other"] = "other"


class ExternalCacheRequest(Schema):
    source: Literal["open_food_facts"]
    source_food_id: str = Field(min_length=3, max_length=120)
