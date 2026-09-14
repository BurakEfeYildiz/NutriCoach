"""Resolve model suggestions using owned DB records, then apply one atomic batch."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import unicodedata

from sqlalchemy.orm import Session

from app.models.nutrition import Meal, MealItem, NUTRIENTS
from app.schemas.chat import ActionResult
from app.schemas.intents import IntentPlan, MealCreate, MealDelete, MealUpdate, ProfileUpdate, TargetSelector, WeightCreate
from app.schemas.nutrition import ItemWrite, MealReplace, MealWrite, WeightWrite
from app.schemas.user import ProfileWrite
from app.services import nutrition, users, weights


class ClarificationNeeded(Exception):
    pass


def normalized(value: str) -> str:
    return unicodedata.normalize('NFKC', value).casefold().replace('i\u0307', 'i').strip()


def normalized_unit(value: str) -> str:
    unit = normalized(value)
    return {'gram': 'g', 'gr': 'g', 'grams': 'g', 'mililitre': 'ml', 'milliliter': 'ml', 'kilogram': 'kg'}.get(unit, unit)


def resolve_target(session: Session, user_id: str, selector: TargetSelector, now: datetime) -> tuple[Meal, MealItem]:
    user = users.get_user(session, user_id)
    end_day = selector.day or nutrition.local_date(user, now)
    start_day = selector.day or end_day - timedelta(days=6)
    matches = []
    for meal in nutrition.range_meals(session, user, start_day, end_day):
        for item in meal.items:
            if normalized(selector.item_name) in normalized(item.name):
                matches.append((meal, item))
    if not matches:
        raise ClarificationNeeded('Bu yiyeceğe ait kayıt bulamadım. Yiyeceğin kayıtlı adını ve yediğin günü belirtir misin?')
    if len(matches) > 1:
        raise ClarificationNeeded('Birden fazla kayıt eşleşiyor. Hangi gün ve hangi öğündeki yiyeceği kastettiğini belirtir misin? Aynı gün birden fazla eşleşme varsa şimdilik öğün API’sinden düzenleyebilirsin.')
    return matches[0]


def updated_meal(meal: Meal, items: list[ItemWrite]) -> MealReplace:
    return MealReplace(**{**MealWrite.model_validate(meal).model_dump(), 'items': items, 'expected_version': meal.version})


def apply_actions(session: Session, user_id: str, plan: IntentPlan, now: datetime, original_text: str) -> list[ActionResult]:
    # Resolve all selectors before the first write. Any failure rolls back the entire batch.
    resolved = {}
    touched = set()
    for index, action in enumerate(plan.actions):
        if isinstance(action, (MealUpdate, MealDelete)):
            meal, item = resolve_target(session, user_id, action.target, now)
            if meal.id in touched:
                raise ClarificationNeeded('Aynı öğün için birden fazla değişiklik var. Bu aşamada değişiklikleri ayrı mesajlarla gönderir misin?')
            touched.add(meal.id)
            if isinstance(action, MealUpdate) and normalized_unit(action.unit) != normalized_unit(item.unit):
                raise ClarificationNeeded(f'Bu kaydın birimi {item.unit}. Yeni miktarı aynı birimde belirtir misin?')
            resolved[index] = meal, item
    results = []
    for index, action in enumerate(plan.actions):
        if isinstance(action, MealCreate):
            values = action.meal.model_dump()
            values['occurred_at'] = action.meal.occurred_at or now
            values['original_description'] = original_text
            values['nutrition_source'] = 'estimate'
            for item in values['items']:
                item['source'] = 'estimate'
            meal = nutrition.create_meal(session, user_id, MealWrite.model_validate(values), commit=False)
            results.append(ActionResult(type=action.type, record_id=meal.id, version=meal.version))
        elif isinstance(action, (MealUpdate, MealDelete)):
            meal, target = resolved[index]
            if isinstance(action, MealDelete) and (action.scope == 'meal' or len(meal.items) == 1):
                nutrition.delete_meal(session, user_id, meal.id, commit=False)
                results.append(ActionResult(type=action.type, record_id=meal.id))
                continue
            items = []
            for item in meal.items:
                data = ItemWrite.model_validate(item)
                if item.id == target.id:
                    if isinstance(action, MealDelete):
                        continue
                    ratio = action.quantity / item.quantity
                    data = ItemWrite.model_validate({
                        **data.model_dump(), 'quantity': action.quantity, 'source': 'user_corrected',
                        'assumptions': 'Önceki porsiyonun besin değerleri yeni miktara orantılı ölçeklendi.',
                        **{key: (getattr(item, key) * ratio).quantize(Decimal('.01'), rounding=ROUND_HALF_UP) for key in NUTRIENTS},
                    })
                items.append(data)
            replacement = updated_meal(meal, items)
            replacement.nutrition_source = 'user_corrected'
            meal = nutrition.replace_meal(session, user_id, meal.id, replacement, commit=False)
            results.append(ActionResult(type=action.type, record_id=meal.id, version=meal.version))
        elif isinstance(action, WeightCreate):
            weight = weights.create_weight(session, user_id, WeightWrite.model_validate({
                **action.weight.model_dump(), 'occurred_at': action.weight.occurred_at or now,
            }), commit=False)
            results.append(ActionResult(type=action.type, record_id=weight.id))
        elif isinstance(action, ProfileUpdate):
            user = users.get_user(session, user_id)
            profile = ProfileWrite.model_validate(user.profile).model_dump()
            profile.update(action.changes.model_dump(exclude_unset=True))
            users.replace_profile(session, user_id, ProfileWrite.model_validate(profile), commit=False)
            results.append(ActionResult(type=action.type, record_id=user_id))
    return results
