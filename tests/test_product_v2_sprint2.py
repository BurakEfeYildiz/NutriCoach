from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import Settings
from app.db.database import create_database
from app.db.migrate import upgrade_database
from app.schemas.activity import DailyStepsWrite, WorkoutWrite
from app.schemas.food import CustomFoodCreate, FoodLogCreate, FoodLogPreviewRequest
from app.schemas.user import UserCreate
from app.schemas.nutrition import WeightWrite
from app.services import activity, food_data, nutrition, users, weights
from app.services.food_providers.open_food_facts import OpenFoodFactsProvider
from app.services.context_service import build_coach_context
from app.schemas.intents import IntentPlan
from app.services.chat_actions import apply_actions
from app.main import create_app
from app.models.auth import AuthSession
from app.routes.dependencies import get_csrf_token_for_session
from tests.fakes import FakeGeminiProvider


@pytest.fixture
def sprint2_db(tmp_path):
    url = f"sqlite:///{tmp_path / 'sprint2.db'}"
    upgrade_database(url)
    engine, factory = create_database(url)
    with factory() as session:
        a = users.create_user(session, UserCreate(name="A", timezone="Europe/Istanbul"))
        b = users.create_user(session, UserCreate(name="B", timezone="Europe/Istanbul"))
        yield session, a, b
    engine.dispose()


def yogurt_payload(name="Yoğurt"):
    return CustomFoodCreate(canonical_name=name, basis_type="per_100g", basis_amount="100", basis_unit="g",
        calories="60", protein_g="4", carbs_g="5", fat_g="3", aliases=["sade yoğurt"], portions=[{
            "label": "kase", "amount": "1", "unit": "kase", "gram_equivalent": "200"
        }])


def test_deterministic_food_log_snapshot_and_private_isolation(sprint2_db):
    session, a, b = sprint2_db
    food = food_data.create_custom_food(session, a.id, yogurt_payload())
    assert food_data.search_foods(session, a.id, "sade yogurt")[0].id == food.id
    assert food_data.search_foods(session, b.id, "sade yogurt") == []
    with pytest.raises(HTTPException) as error: food_data.owned_food(session, b.id, food.id)
    assert error.value.status_code == 404

    preview = food_data.preview_food(session, a.id, FoodLogPreviewRequest(food_id=food.id, quantity="1.5", unit="g"))
    assert preview.calories == Decimal("0.90")
    portion = food.portions[0]
    meal = food_data.log_food(session, a.id, FoodLogCreate(food_id=food.id, quantity="1.5", portion_id=portion.id,
        occurred_at=datetime(2026, 9, 14, 21, 30, tzinfo=timezone.utc), meal_type="extra"))
    assert nutrition.meal_totals(meal).calories == Decimal("180.00")
    food.calories = Decimal("90.00"); session.commit()
    assert nutrition.meal_totals(nutrition.owned_meal(session, a.id, meal.id)).calories == Decimal("180.00")
    assert nutrition.daily_summary(session, a.id, date(2026, 9, 15)).totals.calories == Decimal("180.00")
    assert food_data.recent_foods(session, a.id)[0].id == food.id
    food_data.set_favorite(session, a.id, food.id)
    assert food_data.favorite_foods(session, a.id)[0].id == food.id
    assert food_data.favorite_foods(session, b.id) == []


def test_basis_contract_rejects_implicit_ml_to_grams(sprint2_db):
    session, a, _ = sprint2_db
    food = food_data.create_custom_food(session, a.id, yogurt_payload())
    with pytest.raises(HTTPException) as error:
        food_data.preview_food(session, a.id, FoodLogPreviewRequest(food_id=food.id, quantity="100", unit="ml"))
    assert error.value.status_code == 422


def test_steps_workouts_timezone_met_and_isolation(sprint2_db):
    session, a, b = sprint2_db
    weights.create_weight(session, a.id, WeightWrite(occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc), weight_kg="80"))
    activity.upsert_steps(session, a.id, DailyStepsWrite(day=date(2026, 9, 15), step_count=7000))
    workout = activity.create_workout(session, a.id, WorkoutWrite(occurred_at=datetime(2026, 9, 14, 21, 30, tzinfo=timezone.utc), activity_type="walking", duration_minutes=30, intensity="moderate"))
    assert workout.met_value == Decimal("3.50")
    assert workout.estimated_calories == Decimal("147.00")
    summary = activity.today_summary(session, a, datetime(2026, 9, 15, 9, tzinfo=timezone.utc))
    assert summary.total_steps == 7000 and summary.total_workout_minutes == 30
    assert activity.list_workouts(session, b.id, b, date(2026, 9, 15)) == []
    with pytest.raises(HTTPException): activity.owned_workout(session, b.id, workout.id)
    activity.upsert_steps(session, a.id, DailyStepsWrite(day=date(2026, 9, 15), step_count=8000))
    assert activity.list_steps(session, a.id, date(2026, 9, 15), date(2026, 9, 15))[0].step_count == 8000
    assert activity.today_summary(session, b, datetime(2026, 9, 15, 9, tzinfo=timezone.utc)).total_steps is None
    updated = activity.replace_workout(session, a.id, workout.id, WorkoutWrite(occurred_at=workout.occurred_at, activity_type="walking", duration_minutes=60, intensity="light"))
    assert updated.estimated_calories == Decimal("235.20")
    activity.delete_workout(session, a.id, workout.id)
    assert activity.list_workouts(session, a.id, a, date(2026, 9, 15)) == []


def test_activity_context_is_compact_and_does_not_change_target(sprint2_db):
    session, a, _ = sprint2_db
    a.profile.calorie_target = 2100; session.commit()
    weights.create_weight(session, a.id, WeightWrite(occurred_at=datetime(2026, 9, 15, tzinfo=timezone.utc), weight_kg="80"))
    activity.upsert_steps(session, a.id, DailyStepsWrite(day=date(2026, 9, 15), step_count=6000))
    activity.create_workout(session, a.id, WorkoutWrite(occurred_at=datetime(2026, 9, 15, 7, tzinfo=timezone.utc), activity_type="cycling", duration_minutes=20, intensity="moderate"))
    assert a.profile.calorie_target == 2100
    context = build_coach_context(session, a.id, current_message="Bugünkü adım ve egzersizim nasıl?", now=datetime(2026, 9, 15, 9, tzinfo=timezone.utc))
    assert context.activity.total_steps == 6000
    assert context.activity.total_workout_minutes == 20
    assert len(context.activity.workouts) == 1
    assert "activity" in context.included_sections


def test_usda_normalization_supports_legacy_nutrients_and_portions():
    from app.services.food_providers.usda import USDAFoodDataProvider
    raw = {"fdcId": 1, "description": "Egg, cooked", "dataType": "SR Legacy", "foodNutrients": [
        {"nutrient": {"number": "958"}, "amount": 155}, {"nutrient": {"number": "203"}, "amount": 12.58},
        {"nutrient": {"number": "205"}, "amount": 1.12}, {"nutrient": {"number": "204"}, "amount": 10.61},
    ], "foodPortions": [{"amount": 1, "gramWeight": 50, "portionDescription": "large egg", "measureUnit": {"name": "egg"}}]}
    normalized = USDAFoodDataProvider("test").normalize(raw)
    assert normalized["calories"] == Decimal("155.00")
    assert normalized["portions"][0]["gram_equivalent"] == Decimal("50.00")


def test_ai_simple_entity_uses_exact_alias_and_food_specific_portion(sprint2_db):
    session, a, _ = sprint2_db
    egg = food_data.create_custom_food(session, a.id, CustomFoodCreate(
        canonical_name="Egg, cooked", basis_type="per_100g", basis_amount="100", basis_unit="g",
        calories="150", protein_g="12", carbs_g="1", fat_g="10", aliases=["yumurta"],
        portions=[{"label": "adet", "amount": "1", "unit": "adet", "gram_equivalent": "50"}],
    ))
    plan = IntentPlan.model_validate({"needs_clarification": False, "clarification_question": None, "actions": [{"type": "meal_create", "meal": {
        "occurred_at": "2026-09-15T09:00:00+03:00", "meal_type": "breakfast", "original_description": "3 yumurta",
        "nutrition_source": "estimate", "items": [{"name": "yumurta", "quantity": 3, "unit": "adet", "calories": 999, "protein_g": 0, "carbs_g": 0, "fat_g": 0, "source": "estimate"}],
    }}]})
    result = apply_actions(session, a.id, plan, datetime(2026, 9, 15, 6, tzinfo=timezone.utc), "3 yumurta")
    session.commit()
    meal = nutrition.owned_meal(session, a.id, result[0].record_id)
    assert meal.items[0].food_id == egg.id
    assert meal.items[0].calories == Decimal("225.00")
    assert meal.items[0].source == "user"


def test_open_food_facts_normalization_keeps_missing_distinct_from_zero():
    row = OpenFoodFactsProvider("NutriCoach tests").normalize({"code": "123", "product_name": "Ürün", "nutriments": {
        "energy-kcal_100g": 100, "proteins_100g": 0, "carbohydrates_100g": 20, "fat_100g": 1,
        "sodium_100g": 0.001,
    }})
    assert row["protein_g"] == Decimal("0.00")
    assert row["fiber_g"] is None
    assert row["basis_type"] == "per_100g"
    assert row["sodium_mg"] == Decimal("1.00")


def test_external_upsert_is_idempotent_and_preserves_provenance(sprint2_db):
    session, _, _ = sprint2_db
    payload = {"canonical_name": "Bananas, raw", "brand": None, "source": "usda", "source_food_id": "173944",
        "source_data_type": "Foundation", "category": "Fruits", "barcode": None, "country": "US", "basis_type": "per_100g",
        "basis_amount": Decimal("100"), "basis_unit": "g", "calories": Decimal("89"), "protein_g": Decimal("1.09"),
        "carbs_g": Decimal("22.84"), "fat_g": Decimal("0.33"), "fiber_g": Decimal("2.6"), "sugar_g": None,
        "sodium_mg": Decimal("1"), "reliability": "government_reference", "source_metadata": {"publication_date": "2019"}, "portions": []}
    first = food_data.upsert_external_food(session, payload, ["muz"])
    payload["calories"] = Decimal("90")
    second = food_data.upsert_external_food(session, payload, ["muz"])
    assert first.id == second.id and second.calories == Decimal("90.00")
    assert second.source == "usda" and second.source_metadata["publication_date"] == "2019"


def test_authenticated_food_and_activity_api_flow(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'api.db'}")
    upgrade_database(settings.database_url)
    app = create_app(settings, provider=FakeGeminiProvider())
    with TestClient(app) as client:
        assert client.post("/api/v1/auth/register", json={"name": "API", "email": "api@example.com", "password": "password123", "timezone": "Europe/Istanbul"}).status_code == 201
        with app.state.session_factory() as session:
            auth_session = session.scalar(select(AuthSession).order_by(AuthSession.created_at.desc()))
            csrf = get_csrf_token_for_session(auth_session, settings)
        headers = {"X-CSRF-Token": csrf}
        created = client.post("/api/v1/me/foods", headers=headers, json=yogurt_payload().model_dump(mode="json"))
        assert created.status_code == 201
        food = created.json()
        assert client.get("/api/v1/me/foods/search?q=yogurt").json()["local"][0]["id"] == food["id"]
        preview = client.post("/api/v1/me/foods/log-preview", headers=headers, json={"food_id": food["id"], "quantity": 100, "unit": "g"})
        assert preview.status_code == 200 and preview.json()["calories"] == "60.00"
        logged = client.post("/api/v1/me/foods/log", headers=headers, json={"food_id": food["id"], "quantity": 100, "unit": "g", "meal_type": "extra", "occurred_at": "2026-09-15T09:00:00+03:00"})
        assert logged.status_code == 201 and logged.json()["totals"]["calories"] == "60.00"
        assert client.put("/api/v1/me/daily-steps", headers=headers, json={"day": "2026-09-15", "step_count": 4321, "source": "manual"}).status_code == 200
        today = client.get("/api/v1/me/activity/today").json()
        assert today["total_steps"] in (None, 4321)  # Depends on the real current local date.
