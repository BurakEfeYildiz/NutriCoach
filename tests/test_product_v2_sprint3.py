"""Targeted adaptive-coach checks; no provider or browser matrix."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.db.database import create_database
from app.db.migrate import upgrade_database
from app.core.config import Settings
from app.main import create_app
from tests.fakes import FakeGeminiProvider
from app.models.activity import DailySteps, Workout
from app.models.nutrition import Meal, MealItem, WeightLog
from app.schemas.food import CustomFoodCreate
from app.schemas.recipe import DietaryExclusions, RecipeCreate
from app.schemas.user import UserCreate
from app.services import adaptive_analytics as analytics, food_data, recipes, users
from app.services.context_service import build_coach_context

TODAY = date(2026, 9, 15)
NOW = datetime(2026, 9, 15, 19, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    url = f"sqlite:///{tmp_path / 'adaptive.db'}"
    upgrade_database(url)
    engine, factory = create_database(url)
    with factory() as session:
        user = users.create_user(session, UserCreate(name="A", timezone="Europe/Istanbul"))
        other = users.create_user(session, UserCreate(name="B", timezone="Europe/Istanbul"))
        user.profile.calorie_target = 2000
        user.profile.protein_target_g = 100
        user.profile.carb_target_g = 200
        user.profile.fat_target_g = 60
        user.profile.estimated_expenditure_kcal = 2300
        user.profile.goal_type = "lose"
        user.profile.goal_weight_kg = Decimal("75")
        user.profile.pace_percent_per_week = Decimal("0.50")
        user.profile.plan_status = "active"
        session.commit()
        yield session, user, other
    engine.dispose()


def add_meal(session, user, day, hour, meal_type, calories, protein=30, carbs=50, fat=15):
    meal = Meal(user_id=user.id, occurred_at=datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=hour),
        meal_type=meal_type, original_description=meal_type, items=[MealItem(user_id=user.id,
            name=meal_type, quantity=Decimal("1"), unit="porsiyon", calories=Decimal(calories),
            protein_g=Decimal(protein), carbs_g=Decimal(carbs), fat_g=Decimal(fat))])
    session.add(meal)
    return meal


def add_complete_day(session, user, day, breakfast=800, lunch=1100, extra=100):
    add_meal(session, user, day, 6, "breakfast", breakfast, protein=35)
    add_meal(session, user, day, 12, "lunch", lunch, protein=60)
    if extra:
        add_meal(session, user, day, 14, "extra", extra, protein=5)


def test_missing_days_partial_days_timezone_and_usable_averages(db):
    session, user, _ = db
    empty = analytics.build_dashboard(session, user.id, NOW)
    assert empty.today_quality.status == "none"
    assert empty.today_quality.totals is None
    assert empty.nutrition_7d.average_over_usable_days is None
    assert empty.nutrition_7d.missing_days == 7
    # 21:30 UTC belongs to the following nutrition day in Istanbul.
    add_meal(session, user, TODAY - timedelta(days=3), 12, "breakfast", "500")
    add_meal(session, user, TODAY - timedelta(days=2), 21, "breakfast", "500")
    add_complete_day(session, user, TODAY - timedelta(days=1), extra=100)
    session.commit()
    result = analytics.build_dashboard(session, user.id, NOW)
    assert result.nutrition_7d.logged_days == 2  # midnight meal joins the following local day
    assert result.nutrition_7d.usable_days == 1
    assert result.nutrition_7d.average_over_usable_days.calories == Decimal("2500.00")
    assert result.nutrition_7d.calorie_hit_days == 0  # very low/high intake is not rewarded
    assert result.nutrition_7d.extras_average_calories == Decimal("100.00")
    assert result.today_quality.status == "none"


def test_weight_ewma_irregular_sparse_confidence_and_relative_change(db):
    session, user, _ = db
    for offset, kg in [(28, "80"), (21, "79.5"), (14, "79"), (7, "78.5"), (0, "78")]:
        session.add(WeightLog(user_id=user.id, occurred_at=NOW - timedelta(days=offset), weight_kg=Decimal(kg)))
    session.commit()
    trend = analytics.build_dashboard(session, user.id, NOW).weight
    assert trend.current_raw_weight_kg == Decimal("78")
    assert Decimal("78") < trend.current_trend_weight_kg < Decimal("80")
    assert trend.trend_weight_7d_ago_kg is not None
    assert trend.weekly_change_kg < 0
    assert trend.weekly_change_percent == analytics.q(trend.weekly_change_kg / trend.trend_weight_7d_ago_kg * 100)
    assert trend.confidence == "medium"
    assert session.query(WeightLog).filter(WeightLog.user_id == user.id).count() == 5
    other = analytics.build_dashboard(session, db[2].id, NOW)
    assert other.weight.current_raw_weight_kg is None
    assert other.nutrition_7d.average_over_usable_days is None


def test_activity_recorded_day_average_and_workout_window(db):
    session, user, _ = db
    session.add_all([DailySteps(user_id=user.id, day=TODAY, step_count=5000),
        DailySteps(user_id=user.id, day=TODAY - timedelta(days=2), step_count=9000),
        Workout(user_id=user.id, occurred_at=NOW - timedelta(days=1), activity_type="walking",
            duration_minutes=30, intensity="moderate", estimated_calories=Decimal("100"))])
    session.commit()
    activity = analytics.build_dashboard(session, user.id, NOW).activity
    assert activity.steps_today == 5000
    assert activity.days_7.step_recorded_days == 2
    assert activity.days_7.average_steps_over_recorded_days == Decimal("7000.00")
    assert activity.steps_vs_7d_average is None  # needs five recorded days
    assert activity.days_7.workout_count == 1
    assert activity.days_7.workout_minutes == 30
    assert activity.days_7.estimated_workout_calories == Decimal("100")


def test_adaptive_expenditure_guards_review_insights_and_no_target_mutation(db):
    session, user, _ = db
    before = user.profile.calorie_target
    for offset in range(29):
        add_complete_day(session, user, TODAY - timedelta(days=offset), breakfast=800, lunch=1100, extra=100)
    for offset, kg in [(28, "80"), (23, "79.9"), (18, "79.8"), (13, "79.7"), (8, "79.6"), (4, "79.5"), (0, "79.4")]:
        session.add(WeightLog(user_id=user.id, occurred_at=NOW - timedelta(days=offset), weight_kg=Decimal(kg)))
    session.commit()
    dashboard = analytics.build_dashboard(session, user.id, NOW)
    assert dashboard.nutrition_7d.usable_days == 7
    assert dashboard.nutrition_14d.usable_days == 14
    assert dashboard.nutrition_14d.meal_averages["breakfast"].protein_g == Decimal("35.00")
    assert dashboard.expenditure.source == "adaptive_estimate"
    assert dashboard.expenditure.confidence in {"medium", "high"}
    assert abs(dashboard.expenditure.estimated_expenditure_kcal - Decimal("2300")) <= 150
    assert dashboard.expenditure.usable_overlap_days >= 21
    assert user.profile.calorie_target == before
    assert dashboard.weekly_review.nutrition.usable_days == 7
    assert dashboard.goal.actual_rate_percent_per_week is not None
    assert len(dashboard.insights) <= 3
    assert dashboard.gamification.current_logging_streak >= 7
    assert "five_of_seven_usable_days" in dashboard.gamification.achievements
    assert dashboard.weekly_review.target_suggestion.automatically_applied is False


def test_recipe_structured_totals_exclusions_partial_and_private_access(db):
    session, user, other = db
    food = food_data.create_custom_food(session, user.id, CustomFoodCreate(canonical_name="Test yoğurt",
        basis_type="per_100g", basis_amount="100", basis_unit="g", calories="60", protein_g="4",
        carbs_g="5", fat_g="3", aliases=["yoğurt"], portions=[]))
    structured = recipes.create_recipe(session, user.id, RecipeCreate(name="Yoğurt kasesi", description="",
        servings=2, instructions=["Karıştır."], tags=["ara öğün"], ingredients=[{
            "food_id": food.id, "quantity": "200", "unit": "g", "allergen_tags": ["süt"]}]))
    read = recipes.recipe_read(session, user.id, structured)
    assert read.nutrition_status == "structured"
    assert read.per_serving.calories == Decimal("60.00")
    assert read.ingredients[0].calories == Decimal("120.00")
    assert read.per_serving.protein_g == Decimal("4.00")
    partial = recipes.create_recipe(session, user.id, RecipeCreate(name="Belirsiz tarif", description="",
        servings=1, instructions=["Hazırla."], ingredients=[{"fallback_text": "Ölçülmemiş malzeme",
            "quantity": "1", "unit": "porsiyon"}]))
    assert recipes.recipe_read(session, user.id, partial).per_serving is None
    assert recipes.recipe_read(session, user.id, partial).nutrition_status == "partial"
    with pytest.raises(HTTPException) as error: recipes.owned_recipe(session, other.id, structured.id)
    assert error.value.status_code == 404
    recipes.set_exclusions(session, user.id, DietaryExclusions(foods=["süt"]))
    assert structured.id not in [entry.id for entry in recipes.recommend(session, user.id, now=NOW)]


def test_context_v3_keeps_missing_metrics_and_relevance(db):
    session, user, _ = db
    context = build_coach_context(session, user.id, current_message="Neden kilo veremiyorum?", now=NOW)
    assert context.adaptive is not None
    assert context.adaptive.weight_trend.current_raw_weight_kg is None
    assert context.adaptive.nutrition_7d.average_over_usable_days is None
    assert "recipe_suggestions" not in context.included_sections


def test_adaptive_fallback_and_trend_eta_safety(db):
    session, user, _ = db
    session.add(WeightLog(user_id=user.id, occurred_at=NOW, weight_kg=Decimal("80")))
    add_complete_day(session, user, TODAY)
    session.commit()
    result = analytics.build_dashboard(session, user.id, NOW)
    assert result.expenditure.source == "initial_estimate"
    assert result.expenditure.estimated_expenditure_kcal == Decimal("2300")
    assert result.weight.confidence == "insufficient"
    assert result.goal.trend_eta_earliest is None
    assert result.weekly_review.target_suggestion.action == "insufficient_data"
    assert result.gamification.achievements == ["first_complete_day"]


def test_adaptive_api_requires_current_user(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'api.db'}")
    upgrade_database(settings.database_url)
    app = create_app(settings, provider=FakeGeminiProvider())
    with TestClient(app) as client:
        for endpoint in ("adaptive-dashboard", "weight-trend", "weekly-review", "recipes/recommended"):
            assert client.get(f"/api/v1/me/{endpoint}").status_code == 401
        response = client.post("/api/v1/auth/register", json={"name": "API User", "email": "a@example.com",
            "password": "password123", "timezone": "Europe/Istanbul"})
        assert response.status_code == 201
        dashboard = client.get("/api/v1/me/adaptive-dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["today_quality"]["status"] == "none"
        assert dashboard.json()["nutrition_7d"]["average_over_usable_days"] is None
