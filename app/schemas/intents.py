from datetime import date
from typing import Annotated, Literal, Union

from pydantic import AwareDatetime, Field, model_validator

from app.schemas.nutrition import MealWrite, Positive, WeightWrite
from app.schemas.user import ProfileWrite, Schema


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


class ProfilePatch(ProfileWrite):
    @model_validator(mode='after')
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError('En az bir profil alanı gerekli.')
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
