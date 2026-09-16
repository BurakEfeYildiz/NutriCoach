"""Canonical food search, provenance-preserving upsert and deterministic portion math."""
import re
import unicodedata
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.food import FavoriteFood, Food, FoodAlias, FoodPortion
from app.models.nutrition import Meal, MealItem
from app.models.user import utc_now
from app.schemas.food import CustomFoodCreate, FoodLogCreate, FoodLogPreview, FoodLogPreviewRequest

REQUIRED = ("calories", "protein_g", "carbs_g", "fat_g")


def normalize_term(value: str) -> str:
    value = value.casefold().translate(str.maketrans({"ı": "i"}))
    value = "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def validate_complete(data: dict) -> None:
    if any(data.get(key) is None for key in REQUIRED):
        raise ValueError("Kalori, protein, karbonhidrat ve yağ değerlerinin tamamı gerekli.")
    if any(not Decimal(str(data[key])).is_finite() or Decimal(str(data[key])) < 0 for key in REQUIRED):
        raise ValueError("Besin değerleri negatif olamaz.")


def visible_food_query(user_id: str):
    return or_(Food.owner_user_id.is_(None), Food.owner_user_id == user_id)


def food_read_query():
    return select(Food).options(selectinload(Food.portions), selectinload(Food.aliases))


def owned_food(session: Session, user_id: str, food_id: str) -> Food:
    food = session.scalar(food_read_query().where(Food.id == food_id, visible_food_query(user_id)))
    if not food:
        raise HTTPException(404, "Yiyecek bulunamadı.")
    return food


def search_foods(session: Session, user_id: str, query: str, limit: int = 20) -> list[Food]:
    needle = normalize_term(query)
    if not needle:
        return []
    alias_ids = select(FoodAlias.food_id).where(FoodAlias.normalized_alias.like(f"%{needle}%"))
    stmt = food_read_query().where(
        visible_food_query(user_id), or_(Food.normalized_name.like(f"%{needle}%"), func.lower(Food.brand).like(f"%{needle}%"), Food.id.in_(alias_ids))
    ).limit(min(limit * 3, 60))
    rows = list(session.scalars(stmt).unique())
    def rank(food: Food):
        alias_exact = any(a.normalized_alias == needle for a in food.aliases)
        return (0 if food.normalized_name == needle or alias_exact else 1, 0 if food.normalized_name.startswith(needle) else 1, 0 if food.owner_user_id == user_id else 1, len(food.normalized_name))
    return sorted(rows, key=rank)[:limit]


def upsert_external_food(session: Session, data: dict, aliases: list[str] | None = None, *, commit: bool = True) -> Food:
    validate_complete(data)
    if not normalize_term(data.get("canonical_name") or "") or not data.get("source_food_id"):
        raise ValueError("Kaynak kimliği ve geçerli yiyecek adı gerekli.")
    food = session.scalar(select(Food).where(Food.source == data["source"], Food.source_food_id == data["source_food_id"]))
    values = {k: v for k, v in data.items() if k not in {"portions"}}
    values["normalized_name"] = normalize_term(values["canonical_name"])
    values["owner_user_id"] = None
    values["last_synced_at"] = utc_now()
    if food is None:
        food = Food(**values)
        session.add(food)
        session.flush()
    else:
        for key, value in values.items():
            setattr(food, key, value)
        session.execute(delete(FoodPortion).where(FoodPortion.food_id == food.id))
    for portion in data.get("portions", []):
        session.add(FoodPortion(food_id=food.id, **portion))
    for alias in aliases or []:
        normalized = normalize_term(alias)
        existing = session.scalar(select(FoodAlias).where(FoodAlias.food_id == food.id, FoodAlias.normalized_alias == normalized, FoodAlias.language == "tr"))
        if normalized and not existing:
            session.add(FoodAlias(food_id=food.id, alias=alias, normalized_alias=normalized, language="tr", source="curated"))
    session.commit() if commit else session.flush()
    return session.scalar(food_read_query().where(Food.id == food.id))


def create_custom_food(session: Session, user_id: str, data: CustomFoodCreate) -> Food:
    values = data.model_dump(exclude={"aliases", "portions"})
    food = Food(
        owner_user_id=user_id, normalized_name=normalize_term(data.canonical_name), source="user",
        source_food_id=str(uuid4()), source_data_type="private_custom", reliability="user_entered",
        source_metadata=None, last_synced_at=utc_now(), category=None, barcode=None, country=None, **values,
    )
    session.add(food)
    session.flush()
    seen_aliases = set()
    for alias in data.aliases:
        normalized = normalize_term(alias)
        if normalized and normalized not in seen_aliases:
            seen_aliases.add(normalized)
            session.add(FoodAlias(food_id=food.id, alias=alias, normalized_alias=normalized, language="tr", source="user"))
    for portion in data.portions:
        session.add(FoodPortion(food_id=food.id, source="user", **portion.model_dump()))
    session.commit()
    return session.scalar(food_read_query().where(Food.id == food.id))


def _factor(food: Food, quantity: Decimal, portion: FoodPortion | None, unit: str | None) -> tuple[Decimal, str, str | None]:
    measured = quantity
    label = None
    if portion:
        label = portion.label
        if food.basis_type == "per_100g":
            if portion.gram_equivalent is None: raise HTTPException(422, "Bu porsiyonun gram karşılığı yok.")
            measured = quantity * portion.gram_equivalent / portion.amount
        elif food.basis_type == "per_100ml":
            if portion.ml_equivalent is None: raise HTTPException(422, "Bu porsiyonun ml karşılığı yok.")
            measured = quantity * portion.ml_equivalent / portion.amount
        else:
            if portion.serving_equivalent is None: raise HTTPException(422, "Bu porsiyonun servis karşılığı yok.")
            measured = quantity * portion.serving_equivalent / portion.amount
        return measured / food.basis_amount, portion.unit, label
    expected = {"per_100g": "g", "per_100ml": "ml", "per_serving": "serving"}[food.basis_type]
    if unit != expected:
        raise HTTPException(422, f"Bu yiyecek yalnızca {expected} birimiyle dönüştürülebilir; yoğunluk varsayımı yapılmadı.")
    return measured / food.basis_amount, unit, None


def preview_food(session: Session, user_id: str, data: FoodLogPreviewRequest) -> FoodLogPreview:
    food = owned_food(session, user_id, data.food_id)
    try: validate_complete({key: getattr(food, key) for key in REQUIRED})
    except ValueError as exc: raise HTTPException(422, str(exc)) from exc
    portion = None
    if data.portion_id:
        portion = session.scalar(select(FoodPortion).where(FoodPortion.id == data.portion_id, FoodPortion.food_id == food.id))
        if not portion: raise HTTPException(404, "Porsiyon bulunamadı.")
    factor, unit, label = _factor(food, data.quantity, portion, data.unit)
    q = lambda value: (value * factor).quantize(Decimal(".01"), rounding=ROUND_HALF_UP) if value is not None else None
    return FoodLogPreview(
        food_id=food.id, food_name=food.canonical_name, quantity=data.quantity, unit=unit,
        portion_id=portion.id if portion else None, portion_label=label,
        calories=q(food.calories), protein_g=q(food.protein_g), carbs_g=q(food.carbs_g), fat_g=q(food.fat_g),
        fiber_g=q(food.fiber_g), sugar_g=q(food.sugar_g), sodium_mg=q(food.sodium_mg),
        source=food.source, reliability=food.reliability,
    )


def log_food(session: Session, user_id: str, data: FoodLogCreate) -> Meal:
    preview = preview_food(session, user_id, FoodLogPreviewRequest(**data.model_dump(include={"food_id", "quantity", "portion_id", "unit"})))
    food = owned_food(session, user_id, data.food_id)
    item = MealItem(
        user_id=user_id, food_id=food.id, food_portion_id=preview.portion_id, food_source=food.source,
        source_food_id=food.source_food_id, portion_label=preview.portion_label, name=food.canonical_name,
        quantity=preview.quantity, unit=preview.unit, calories=preview.calories, protein_g=preview.protein_g,
        carbs_g=preview.carbs_g, fat_g=preview.fat_g, source=food.source, assumptions=None,
    )
    meal = Meal(user_id=user_id, occurred_at=data.occurred_at, meal_type=data.meal_type,
                original_description=food.canonical_name, normalized_description=food.normalized_name,
                nutrition_source="structured", confidence=Decimal("1.00"), items=[item])
    session.add(meal); session.commit(); session.refresh(meal)
    return meal


def set_favorite(session: Session, user_id: str, food_id: str) -> FavoriteFood:
    owned_food(session, user_id, food_id)
    row = session.scalar(select(FavoriteFood).where(FavoriteFood.user_id == user_id, FavoriteFood.food_id == food_id))
    if row is None:
        row = FavoriteFood(user_id=user_id, food_id=food_id); session.add(row); session.commit(); session.refresh(row)
    return row


def remove_favorite(session: Session, user_id: str, food_id: str) -> None:
    row = session.scalar(select(FavoriteFood).where(FavoriteFood.user_id == user_id, FavoriteFood.food_id == food_id))
    if not row: raise HTTPException(404, "Favori bulunamadı.")
    session.delete(row); session.commit()


def favorite_foods(session: Session, user_id: str, limit: int = 30) -> list[Food]:
    return list(session.scalars(food_read_query().join(FavoriteFood, FavoriteFood.food_id == Food.id).where(FavoriteFood.user_id == user_id, visible_food_query(user_id)).order_by(FavoriteFood.created_at.desc()).limit(limit)).unique())


def recent_foods(session: Session, user_id: str, limit: int = 20) -> list[Food]:
    ids = select(MealItem.food_id, func.max(Meal.occurred_at).label("last_used")).join(Meal, Meal.id == MealItem.meal_id).where(Meal.user_id == user_id, MealItem.user_id == user_id, MealItem.food_id.is_not(None)).group_by(MealItem.food_id).order_by(func.max(Meal.occurred_at).desc()).limit(limit)
    ordered = list(session.execute(ids))
    foods = {f.id: f for f in session.scalars(food_read_query().where(Food.id.in_([r[0] for r in ordered]), visible_food_query(user_id))).unique()} if ordered else {}
    return [foods[r[0]] for r in ordered if r[0] in foods]
