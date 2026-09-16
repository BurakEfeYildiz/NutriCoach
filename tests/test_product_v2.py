from datetime import date, datetime, timezone
from decimal import Decimal
import re

from fastapi.testclient import TestClient
import pytest

from app.core.config import Settings
from app.db.migrate import upgrade_database
from app.main import create_app
from app.services.context_service import build_coach_context
from app.services.nutrition_goal_service import (
    GoalInputs,
    calculate_bmr,
    calculate_plan,
    estimate_initial_expenditure,
    percent_to_kg_per_week,
    round_five,
)
from app.services.users import _local_today
from tests.fakes import FakeGeminiProvider


@pytest.fixture
def product_env(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'product.db'}", gemini_api_key="TEST")
    upgrade_database(settings.database_url)
    app = create_app(settings, provider=FakeGeminiProvider())
    with TestClient(app) as client:
        registered = client.post("/api/v1/auth/register", json={"name": "Plan User", "email": "plan@example.com", "password": "password123", "timezone": "Europe/Istanbul"})
        user_id = registered.json()["id"]
        page = client.get("/onboarding")
        csrf = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.text).group(1)
        yield client, app, user_id, {"X-CSRF-Token": csrf}


def onboarding_payload(**changes):
    payload = {
        "birth_date": "1990-01-01", "biological_sex": "male", "height_cm": "180.0",
        "current_weight_kg": "80.00", "target_weight_kg": "72.00", "goal_type": "lose",
        "activity_level": "moderate", "training_frequency": "three_four",
        "pace_percent_per_week": "0.50", "pregnancy_or_breastfeeding": False,
    }
    payload.update(changes)
    return payload


def test_mifflin_st_jeor_and_deterministic_plan():
    assert calculate_bmr(Decimal("80"), Decimal("180"), 36, "male") == Decimal("1750.00")
    inputs = GoalInputs(date(1990, 1, 1), "male", Decimal("180"), Decimal("80"), Decimal("72"), "lose", "moderate", "three_four", Decimal("0.50"))
    first = calculate_plan(inputs, date(2026, 9, 15))
    second = calculate_plan(inputs, date(2026, 9, 15))
    assert first == second
    assert first.expenditure_source == "initial_estimate"
    assert first.eta_source == "planned_range"
    assert first.planned_eta_earliest < first.planned_eta_latest
    assert first.daily_calorie_target > 0
    assert all(value > 0 for value in (first.protein_target_g, first.carbohydrate_target_g, first.fat_target_g))


def test_plan_date_uses_user_timezone():
    user = type("UserStub", (), {"timezone": "Europe/Istanbul"})()
    assert _local_today(user, datetime(2026, 9, 14, 21, 30, tzinfo=timezone.utc)) == date(2026, 9, 15)


def test_expenditure_pace_and_rounding_helpers():
    assert estimate_initial_expenditure(Decimal("1750"), "moderate") == Decimal("2712.50")
    assert percent_to_kg_per_week(Decimal("80"), Decimal("0.50")) == Decimal("0.40")
    assert round_five(Decimal("2037.48")) == 2035


def test_maintenance_gain_and_guardrail_plans():
    base = dict(birth_date=date(1990, 1, 1), biological_sex="female", height_cm=Decimal("165"), current_weight_kg=Decimal("60"), activity_level="light", training_frequency="one_two", pregnancy_or_breastfeeding=False)
    maintain = calculate_plan(GoalInputs(**base, target_weight_kg=Decimal("60"), goal_type="maintain", pace_percent_per_week=Decimal("0")), date(2026, 9, 15))
    gain = calculate_plan(GoalInputs(**base, target_weight_kg=Decimal("65"), goal_type="gain", pace_percent_per_week=Decimal("0.25")), date(2026, 9, 15))
    constrained = calculate_plan(GoalInputs(**{**base, "current_weight_kg": Decimal("40"), "height_cm": Decimal("150")}, target_weight_kg=Decimal("35"), goal_type="lose", pace_percent_per_week=Decimal("0.75")), date(2026, 9, 15))
    assert maintain.planned_rate_kg_per_week == 0 and maintain.planned_eta_earliest is None
    assert gain.daily_calorie_target > gain.estimated_expenditure_kcal
    assert gain.planned_eta_earliest < gain.planned_eta_latest
    assert constrained.status == "constrained"
    assert constrained.daily_calorie_target >= 1200


def test_registration_is_incomplete_then_onboarding_creates_snapshot_and_weight(product_env):
    client, _, _, headers = product_env
    initial = client.get("/api/v1/me/onboarding").json()
    assert initial["completed"] is False
    assert "current_weight_kg" in initial["missing_fields"]
    response = client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload())
    assert response.status_code == 200
    plan = response.json()
    assert plan["onboarding_complete"] is True
    assert plan["current_weight_kg"] == "80.00"
    assert plan["calculation_version"] == "msj-v1"
    assert plan["expenditure_source"] == "initial_estimate"
    assert client.get("/api/v1/me/weight-logs/current").json()["weight_kg"] == "80.00"
    assert client.get("/", follow_redirects=False).headers["location"] == "/today"


def test_partial_profile_stays_incomplete(product_env):
    client, _, _, headers = product_env
    response = client.put("/api/v1/me/profile", headers=headers, json={"height_cm": 180})
    assert response.status_code == 200
    state = client.get("/api/v1/me/onboarding").json()
    assert state["completed"] is False
    assert "height_cm" not in state["missing_fields"]
    assert "birth_date" in state["missing_fields"]


def test_new_latest_weight_recalculates_plan_but_older_log_does_not(product_env):
    client, _, _, headers = product_env
    client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload())
    original = client.get("/api/v1/me/nutrition-plan").json()
    newer = client.post("/api/v1/me/weight-logs", headers=headers, json={"occurred_at": "2026-09-16T08:00:00+03:00", "weight_kg": "78.00"})
    assert newer.status_code == 201
    changed = client.get("/api/v1/me/nutrition-plan").json()
    assert changed["current_weight_kg"] == "78.00"
    assert changed["bmr_kcal"] != original["bmr_kcal"]
    client.post("/api/v1/me/weight-logs", headers=headers, json={"occurred_at": "2025-01-01T08:00:00+03:00", "weight_kg": "95.00"})
    assert client.get("/api/v1/me/nutrition-plan").json()["current_weight_kg"] == "78.00"


def test_nutrition_profile_update_recalculates_snapshot(product_env):
    client, _, _, headers = product_env
    client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload())
    before = client.get("/api/v1/me/nutrition-plan").json()
    payload = onboarding_payload(activity_level="sedentary")
    payload.pop("current_weight_kg")
    updated = client.put("/api/v1/me/nutrition-profile", headers=headers, json=payload)
    assert updated.status_code == 200
    assert updated.json()["estimated_expenditure_kcal"] < before["estimated_expenditure_kcal"]
    assert updated.json()["calculation_version"] == before["calculation_version"]


@pytest.mark.parametrize("changes", [
    {"current_weight_kg": "-1"},
    {"pace_percent_per_week": "0.90"},
    {"goal_type": "lose", "target_weight_kg": "90"},
    {"birth_date": "2030-01-01"},
])
def test_invalid_onboarding_is_rejected_without_completion(product_env, changes):
    client, _, _, headers = product_env
    response = client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload(**changes))
    assert response.status_code == 422
    assert client.get("/api/v1/me/onboarding").json()["completed"] is False
    assert client.get("/api/v1/me/weight-logs/current").json() is None


@pytest.mark.parametrize("changes,status", [
    ({"birth_date": "2010-01-01"}, "unsupported_minor"),
    ({"pregnancy_or_breastfeeding": True, "biological_sex": "female"}, "unsupported_pregnancy_breastfeeding"),
])
def test_unsupported_groups_are_saved_without_automatic_targets(product_env, changes, status):
    client, _, _, headers = product_env
    response = client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload(**changes))
    assert response.status_code == 200
    plan = response.json()
    assert plan["status"] == status
    assert plan["daily_calorie_target"] is None
    assert plan["constraint_reason"]


def test_coach_context_contains_profile_plan_and_direct_remaining(product_env):
    client, app, user_id, headers = product_env
    client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload())
    with app.state.session_factory() as session:
        context = build_coach_context(session, user_id, current_message="Bugün kalori ve hedef durumum nasıl?", now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
    assert context.profile.goal_type == "lose"
    assert context.profile.current_weight_kg == Decimal("80.00")
    assert context.plan.calculation_version == "msj-v1"
    assert context.plan.planned_rate_percent_per_week == Decimal("0.5")
    assert context.today.has_records is False
    assert context.today.totals is None
    assert context.today.remaining_calories is None


def test_coach_context_sends_consumed_and_remaining_macros_without_llm_math(product_env):
    client, app, user_id, headers = product_env
    plan = client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload()).json()
    meal = {"occurred_at": "2026-09-15T12:00:00+03:00", "meal_type": "lunch", "original_description": "Test öğünü", "items": [{"name": "Öğün", "quantity": "1", "unit": "porsiyon", "calories": "500", "protein_g": "30", "carbs_g": "50", "fat_g": "15"}]}
    assert client.post("/api/v1/me/meals", headers=headers, json=meal).status_code == 201
    with app.state.session_factory() as session:
        context = build_coach_context(session, user_id, current_message="Bugün kalan kalori ve makrolarım?", now=datetime(2026, 9, 15, 12, tzinfo=timezone.utc))
    assert context.today.calories_consumed == Decimal("500.00")
    assert context.today.protein_consumed_g == Decimal("30.00")
    assert context.today.remaining_calories == Decimal(str(plan["daily_calorie_target"])) - Decimal("500")
    assert context.today.remaining_protein_g == Decimal(plan["protein_target_g"]) - Decimal("30")


def test_account_update_does_not_change_nutrition_profile(product_env):
    client, _, _, headers = product_env
    client.put("/api/v1/me/onboarding", headers=headers, json=onboarding_payload())
    before = client.get("/api/v1/me/nutrition-plan").json()
    updated = client.patch("/api/v1/me/account", headers=headers, json={"name": "Yeni Ad", "email": "new@example.com", "timezone": "Europe/Istanbul"})
    assert updated.status_code == 200
    after = client.get("/api/v1/me/nutrition-plan").json()
    assert after == before


def test_authenticated_plan_isolation_between_users(product_env):
    client_a, app, _, headers_a = product_env
    client_a.put("/api/v1/me/onboarding", headers=headers_a, json=onboarding_payload(current_weight_kg="80", target_weight_kg="72"))
    with TestClient(app) as client_b:
        registered = client_b.post("/api/v1/auth/register", json={"name": "User B", "email": "user-b@example.com", "password": "password123", "timezone": "Europe/Istanbul"})
        assert registered.status_code == 201
        plan_b = client_b.get("/api/v1/me/nutrition-plan").json()
        assert plan_b["onboarding_complete"] is False
        assert plan_b["current_weight_kg"] is None
    plan_a = client_a.get("/api/v1/me/nutrition-plan").json()
    assert plan_a["onboarding_complete"] is True
    assert plan_a["current_weight_kg"] == "80.00"
