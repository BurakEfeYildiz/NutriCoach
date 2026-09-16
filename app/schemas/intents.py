from datetime import date, datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.nutrition import MealWrite, Positive, WeightWrite
from app.schemas.user import ActivityLevel, GoalType, Schema, TrainingFrequency


class MealExtraction(MealWrite):
    occurred_at: AwareDatetime | None = None


class WeightExtraction(WeightWrite):
    occurred_at: AwareDatetime | None = None


class TargetSelector(Schema):
    item_name: str = Field(min_length=1, max_length=200, description='Yiyecek adı; veritabanı kimliği değil.')
    day: date | None = Field(default=None, description='Yerel gün; boşsa son 7 gün içinde aranır.')


class NormalChat(Schema):
    type: Literal['normal_chat']


class NutritionQuestion(Schema):
    type: Literal['nutrition_question']


class MealCreate(Schema):
    type: Literal['meal_create']
    meal: MealExtraction


class MealUpdate(Schema):
    type: Literal['meal_update']
    target: TargetSelector
    quantity: Positive
    unit: str = Field(min_length=1, max_length=30)


class MealDelete(Schema):
    type: Literal['meal_delete']
    target: TargetSelector
    scope: Literal['item', 'meal'] = 'item'


class WeightCreate(Schema):
    type: Literal['weight_log_create']
    weight: WeightExtraction


class ProfilePatch(Schema):
    birth_date: date | None = None
    biological_sex: Literal["female", "male"] | None = None
    height_cm: float | None = Field(default=None, ge=100, le=250)
    goal_weight_kg: float | None = Field(default=None, ge=25, le=400)
    activity_level: ActivityLevel | None = None
    goal_type: GoalType | None = None
    training_frequency: TrainingFrequency | None = None
    pace_percent_per_week: float | None = Field(default=None, ge=0, le=0.75)
    pregnancy_or_breastfeeding: bool | None = None

    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError('En az bir profil alanı gerekli.')
        if self.birth_date and self.birth_date > datetime.now(timezone.utc).date():
            raise ValueError('Doğum tarihi gelecekte olamaz.')
        return self


class ProfileUpdate(Schema):
    type: Literal['profile_update']
    changes: ProfilePatch


Action = Annotated[Union[NormalChat, NutritionQuestion, MealCreate, MealUpdate, MealDelete, WeightCreate, ProfileUpdate], Field(discriminator='type')]


class IntentPlan(Schema):
    actions: list[Action] = Field(max_length=5)
    needs_clarification: bool
    clarification_question: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode='after')
    def coherent(self):
        if self.needs_clarification:
            if not self.clarification_question or self.actions:
                raise ValueError('Açıklama gerekiyorsa soru verilmeli ve actions boş olmalı.')
        elif not self.actions or self.clarification_question is not None:
            raise ValueError('Açıklama gerekmiyorsa action listesi dolu, soru null olmalı.')
        return self
