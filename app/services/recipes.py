"""Recipe nutrition and ranking from Food Engine; unresolved ingredients remain partial."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.food import Food
from app.models.memory import Memory
from app.models.recipe import Recipe, RecipeIngredient
from app.schemas.food import FoodLogPreviewRequest
from app.schemas.nutrition import Totals
from app.schemas.recipe import DietaryExclusions, RecipeCreate, RecipeIngredientRead, RecipeRead
from app.services.adaptive_analytics import build_dashboard
from app.services.food_data import normalize_term, owned_food, preview_food
from app.services.users import get_user

CURATED = (
    ("Tavuklu pirinç kasesi", "Tavuk, pişmiş pirinç ve sade yoğurt.", 1,
     ["Pişmiş tavuk ve pirinci bir kasede birleştir.", "Yoğurdu yanında servis et."],
     [("tavuk göğsü", "180"), ("pişmiş pirinç", "150"), ("yoğurt", "100")], ["öğle", "akşam"]),
    ("Yoğurtlu muz ve badem", "Yoğurt, muz ve badem karışımı.", 1,
     ["Yoğurdu kaseye al.", "Muzu ve bademi ekle."],
     [("yoğurt", "200"), ("muz", "120"), ("badem", "20")], ["ara öğün"]),
)


def recipe_query():
    return select(Recipe).options(selectinload(Recipe.ingredients))


def seed_curated(session: Session) -> int:
    """Idempotent catalog-derived examples; no hard-coded nutrient totals."""
    # Global USDA foods only; exact aliases avoid private or mismatched records.
    count = 0
    for name, description, servings, instructions, ingredients, tags in CURATED:
        source_key = normalize_term(name).replace(" ", "-")
        if session.scalar(select(Recipe.id).where(Recipe.source == "curated", Recipe.source_key == source_key)):
            continue
        rows = []
        for alias, quantity in ingredients:
            normalized = normalize_term(alias)
            from app.models.food import FoodAlias
            food = session.scalar(select(Food).join(FoodAlias, FoodAlias.food_id == Food.id).where(
                Food.owner_user_id.is_(None), Food.source == "usda", FoodAlias.normalized_alias == normalized))
            if food is None:
                rows = []
                break
            allergen_tags = ["milk", "süt"] if alias == "yoğurt" else ["nuts", "badem"] if alias == "badem" else []
            rows.append(RecipeIngredient(food_id=food.id, quantity=Decimal(quantity), unit="g",
                                         fallback_text=None, allergen_tags=allergen_tags))
        if not rows:
            continue
        session.add(Recipe(owner_user_id=None, source="curated", source_key=source_key,
            name=name, description=description, servings=servings, instructions=instructions,
            tags=tags, ingredients=rows))
        count += 1
    session.commit()
    return count


def owned_recipe(session: Session, user_id: str, recipe_id: str) -> Recipe:
    row = session.scalar(recipe_query().where(Recipe.id == recipe_id,
        or_(Recipe.owner_user_id.is_(None), Recipe.owner_user_id == user_id)))
    if not row: raise HTTPException(404, "Tarif bulunamadı.")
    return row


def create_recipe(session: Session, user_id: str, data: RecipeCreate) -> Recipe:
    get_user(session, user_id)
    ingredient_rows = []
    for item in data.ingredients:
        if item.food_id:
            owned_food(session, user_id, item.food_id)
            if item.portion_id:
                preview_food(session, user_id, FoodLogPreviewRequest(food_id=item.food_id,
                    portion_id=item.portion_id, quantity=item.quantity))
            else:
                preview_food(session, user_id, FoodLogPreviewRequest(food_id=item.food_id,
                    unit=item.unit, quantity=item.quantity))
        ingredient_rows.append(RecipeIngredient(**item.model_dump()))
    recipe = Recipe(owner_user_id=user_id, source="user", source_key=str(uuid4()),
        name=data.name, description=data.description, servings=data.servings,
        instructions=data.instructions, tags=data.tags, ingredients=ingredient_rows)
    session.add(recipe); session.commit(); session.refresh(recipe)
    return recipe


def _restrictions(session: Session, user_id: str) -> set[str]:
    user = get_user(session, user_id)
    explicit = {normalize_term(value) for value in user.profile.dietary_exclusions or [] if normalize_term(value)}
    memories = list(session.scalars(select(Memory).where(Memory.user_id == user_id,
        Memory.status == "active", Memory.category == "food_dislike").limit(20)))
    return explicit | {normalize_term(row.key.replace("_", " ")) for row in memories if normalize_term(row.key)}


def _excluded(recipe: Recipe, restrictions: set[str], session: Session, user_id: str) -> bool:
    if not restrictions: return False
    for item in recipe.ingredients:
        name = item.fallback_text or ""
        aliases = []
        if item.food_id:
            try: food = owned_food(session, user_id, item.food_id)
            except HTTPException: return True
            name = food.canonical_name
            aliases = [alias.alias for alias in food.aliases]
        terms = [normalize_term(value) for value in [name, *aliases, *(item.allergen_tags or [])]]
        if any(restriction in term.split() or term == restriction or f" {restriction} " in f" {term} "
               for restriction in restrictions for term in terms):
            return True
    return False


def recipe_read(session: Session, user_id: str, recipe: Recipe, remaining: Totals | None = None) -> RecipeRead:
    ingredient_reads = []
    values = []
    complete = True
    for item in recipe.ingredients:
        preview = None
        food = None
        if item.food_id:
            try:
                food = owned_food(session, user_id, item.food_id)
                preview = preview_food(session, user_id, FoodLogPreviewRequest(food_id=food.id,
                    quantity=item.quantity, portion_id=item.portion_id if item.portion_id else None,
                    unit=None if item.portion_id else item.unit))
            except HTTPException:
                preview = None
        if preview is None: complete = False
        else: values.append(preview)
        ingredient_reads.append(RecipeIngredientRead(id=item.id, food_id=item.food_id, portion_id=item.portion_id,
            quantity=item.quantity, unit=item.unit, fallback_text=item.fallback_text,
            allergen_tags=item.allergen_tags or [], name=food.canonical_name if food else item.fallback_text or "Bilinmeyen malzeme",
            provenance=food.source if food else "unresolved_estimate",
            calories=preview.calories if preview else None, protein_g=preview.protein_g if preview else None,
            carbs_g=preview.carbs_g if preview else None, fat_g=preview.fat_g if preview else None))
    totals = None
    if complete:
        totals = Totals(**{key: (sum((getattr(value, key) for value in values), Decimal("0")) / recipe.servings)
            .quantize(Decimal(".01"), rounding=ROUND_HALF_UP) for key in ("calories", "protein_g", "carbs_g", "fat_g")})
    fit = None
    if remaining and totals:
        if totals.calories <= remaining.calories and totals.protein_g <= remaining.protein_g + Decimal("15"):
            fit = f"Kalan {remaining.calories} kcal ve {remaining.protein_g} g protein bağlamına sığıyor."
        else:
            fit = "Kalan hedefe göre porsiyonu uyarlamak gerekebilir."
    return RecipeRead(id=recipe.id, name=recipe.name, description=recipe.description, servings=recipe.servings,
        instructions=recipe.instructions, tags=recipe.tags, source=recipe.source,
        nutrition_status="structured" if complete else "partial", per_serving=totals,
        ingredients=ingredient_reads, why_it_fits=fit)


def recommend(session: Session, user_id: str, meal_type: str | None = None, limit: int = 8, now=None, dashboard=None) -> list[RecipeRead]:
    user = get_user(session, user_id)
    dashboard = dashboard or build_dashboard(session, user_id, now)
    remaining = None
    if dashboard.today_quality.totals and all(getattr(user.profile, key) is not None for key in
        ("calorie_target", "protein_target_g", "carb_target_g", "fat_target_g")):
        current = dashboard.today_quality.totals
        remaining = Totals(calories=Decimal(str(user.profile.calorie_target))-current.calories,
            protein_g=Decimal(str(user.profile.protein_target_g))-current.protein_g if user.profile.protein_target_g is not None else Decimal("0"),
            carbs_g=Decimal(str(user.profile.carb_target_g))-current.carbs_g if user.profile.carb_target_g is not None else Decimal("0"),
            fat_g=Decimal(str(user.profile.fat_target_g))-current.fat_g if user.profile.fat_target_g is not None else Decimal("0"))
    recipes = list(session.scalars(recipe_query().where(or_(Recipe.owner_user_id.is_(None),
        Recipe.owner_user_id == user_id)).limit(60)))
    restrictions = _restrictions(session, user_id)
    ranked = []
    for recipe in recipes:
        if _excluded(recipe, restrictions, session, user_id): continue
        read = recipe_read(session, user_id, recipe, remaining)
        if meal_type and meal_type not in read.tags: continue
        if read.per_serving and remaining:
            cal_penalty = abs(read.per_serving.calories - max(Decimal("0"), remaining.calories * Decimal("0.70")))
            protein_penalty = max(Decimal("0"), remaining.protein_g - read.per_serving.protein_g) * Decimal("2")
            rank = (0, cal_penalty + protein_penalty)
        else:
            rank = (1 if read.per_serving else 2, Decimal("0"))
        ranked.append((rank, read))
    return [read for _, read in sorted(ranked, key=lambda pair: pair[0])[:limit]]


def set_exclusions(session: Session, user_id: str, data: DietaryExclusions) -> DietaryExclusions:
    user = get_user(session, user_id)
    foods = []
    for value in data.foods:
        normalized = normalize_term(value)
        if normalized and len(normalized) <= 80 and normalized not in foods: foods.append(normalized)
    user.profile.dietary_exclusions = foods
    session.commit()
    return DietaryExclusions(foods=foods)
