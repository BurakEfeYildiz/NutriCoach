from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.nutrition import WeightLog
from app.models.user import User, UserProfile
from app.schemas.nutrition import WeightWrite
from app.schemas.user import AccountUpdate, NutritionProfileUpdate, OnboardingComplete, ProfileWrite, UserCreate
from app.services.nutrition_goal_service import GoalCalculationError, GoalInputs, age_on, calculate_plan


def get_user(session: Session, user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı.")
    return user


def create_user(session: Session, data: UserCreate) -> User:
    values = data.model_dump()
    if values["email"]:
        values["email"] = values["email"].lower()
    user = User(**values, profile=UserProfile())
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bu e-posta zaten kayıtlı.")
    return user


def replace_profile(session: Session, user_id: str, data: ProfileWrite, *, commit: bool = True) -> UserProfile:
    profile = get_user(session, user_id).profile
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    session.commit() if commit else session.flush()
    return profile


ONBOARDING_FIELDS = (
    "birth_date",
    "biological_sex",
    "height_cm",
    "goal_weight_kg",
    "goal_type",
    "activity_level",
    "training_frequency",
    "pace_percent_per_week",
    "pregnancy_or_breastfeeding",
)


def latest_weight(session: Session, user_id: str) -> WeightLog | None:
    return session.scalar(
        select(WeightLog)
        .where(WeightLog.user_id == user_id)
        .order_by(WeightLog.occurred_at.desc(), WeightLog.created_at.desc(), WeightLog.id.desc())
        .limit(1)
    )


def onboarding_missing_fields(session: Session, user_id: str) -> list[str]:
    profile = get_user(session, user_id).profile
    missing = [field for field in ONBOARDING_FIELDS if getattr(profile, field) is None]
    if latest_weight(session, user_id) is None:
        missing.append("current_weight_kg")
    return missing


def onboarding_complete(session: Session, user_id: str) -> bool:
    profile = get_user(session, user_id).profile
    return profile.onboarding_completed_at is not None and not onboarding_missing_fields(session, user_id)


def _goal_inputs(profile: UserProfile, weight_kg: Decimal) -> GoalInputs:
    return GoalInputs(
        birth_date=profile.birth_date,
        biological_sex=profile.biological_sex,
        height_cm=Decimal(str(profile.height_cm)),
        current_weight_kg=Decimal(str(weight_kg)),
        target_weight_kg=Decimal(str(profile.goal_weight_kg)),
        goal_type=profile.goal_type,
        activity_level=profile.activity_level,
        training_frequency=profile.training_frequency,
        pace_percent_per_week=Decimal(str(profile.pace_percent_per_week)),
        pregnancy_or_breastfeeding=bool(profile.pregnancy_or_breastfeeding),
    )


def _local_today(user: User, now: datetime | None = None):
    instant = now or datetime.now(timezone.utc)
    return instant.astimezone(ZoneInfo(user.timezone)).date()


def _apply_plan(profile: UserProfile, plan, now: datetime) -> None:
    profile.bmr_kcal = plan.bmr_kcal
    profile.estimated_expenditure_kcal = plan.estimated_expenditure_kcal
    profile.expenditure_source = plan.expenditure_source
    profile.calorie_target = plan.daily_calorie_target
    profile.protein_target_g = plan.protein_target_g
    profile.carb_target_g = plan.carbohydrate_target_g
    profile.fat_target_g = plan.fat_target_g
    profile.preferred_weekly_weight_change_kg = float(plan.planned_rate_kg_per_week)
    profile.planned_rate_kg_per_week = float(plan.planned_rate_kg_per_week)
    profile.planned_eta_earliest = plan.planned_eta_earliest
    profile.planned_eta_latest = plan.planned_eta_latest
    profile.eta_source = plan.eta_source
    profile.plan_status = plan.status
    profile.plan_constraint_reason = plan.constraint_reason
    profile.calculation_version = plan.calculation_version
    profile.targets_recalculated_at = now


def recalculate_targets(session: Session, user_id: str, *, commit: bool = True, allow_reached_goal: bool = False):
    user = get_user(session, user_id)
    weight = latest_weight(session, user_id)
    missing = [field for field in ONBOARDING_FIELDS if getattr(user.profile, field) is None]
    if weight is None:
        missing.append("current_weight_kg")
    if missing:
        raise HTTPException(409, detail={"message": "Beslenme planı için bilgiler eksik.", "missing_fields": missing})
    inputs = _goal_inputs(user.profile, weight.weight_kg)
    reached = allow_reached_goal and (
        (inputs.goal_type == "lose" and inputs.current_weight_kg <= inputs.target_weight_kg)
        or (inputs.goal_type == "gain" and inputs.current_weight_kg >= inputs.target_weight_kg)
    )
    if reached:
        inputs = replace(inputs, goal_type="maintain", target_weight_kg=inputs.current_weight_kg, pace_percent_per_week=Decimal("0"))
    try:
        plan = calculate_plan(inputs, _local_today(user))
    except GoalCalculationError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if reached:
        plan = replace(plan, status="goal_reached", constraint_reason="Hedef kiloya ulaşıldı; plan bakım enerjisine geçirildi.")
    _apply_plan(user.profile, plan, datetime.now(timezone.utc))
    session.commit() if commit else session.flush()
    return plan


def complete_onboarding(session: Session, user_id: str, data: OnboardingComplete):
    user = get_user(session, user_id)
    values = data.model_dump()
    current_weight = values.pop("current_weight_kg")
    values["goal_weight_kg"] = values.pop("target_weight_kg")
    for key, value in values.items():
        setattr(user.profile, key, float(value) if isinstance(value, Decimal) else value)
    now = datetime.now(timezone.utc)
    session.add(WeightLog(user_id=user_id, occurred_at=now, weight_kg=current_weight))
    session.flush()
    recalculate_targets(session, user_id, commit=False)
    user.profile.onboarding_completed_at = now
    session.commit()
    return nutrition_plan(session, user_id)


def update_nutrition_profile(session: Session, user_id: str, data: NutritionProfileUpdate):
    user = get_user(session, user_id)
    values = data.model_dump()
    values["goal_weight_kg"] = values.pop("target_weight_kg")
    for key, value in values.items():
        setattr(user.profile, key, float(value) if isinstance(value, Decimal) else value)
    recalculate_targets(session, user_id, commit=False)
    session.commit()
    return nutrition_plan(session, user_id)


def nutrition_plan(session: Session, user_id: str) -> dict:
    user = get_user(session, user_id)
    profile = user.profile
    weight = latest_weight(session, user_id)
    missing = onboarding_missing_fields(session, user_id)
    complete = profile.onboarding_completed_at is not None and not missing
    age = age_on(profile.birth_date, _local_today(user)) if profile.birth_date else None
    return {
        "onboarding_complete": complete,
        "missing_fields": missing,
        "current_weight_kg": weight.weight_kg if weight else None,
        "age": age,
        "status": profile.plan_status,
        "constraint_reason": profile.plan_constraint_reason,
        "bmr_kcal": profile.bmr_kcal,
        "estimated_expenditure_kcal": profile.estimated_expenditure_kcal,
        "expenditure_source": profile.expenditure_source,
        "daily_calorie_target": profile.calorie_target,
        "protein_target_g": profile.protein_target_g,
        "carbohydrate_target_g": profile.carb_target_g,
        "fat_target_g": profile.fat_target_g,
        "planned_rate_percent_per_week": profile.pace_percent_per_week,
        "planned_rate_kg_per_week": profile.planned_rate_kg_per_week,
        "planned_eta_earliest": profile.planned_eta_earliest,
        "planned_eta_latest": profile.planned_eta_latest,
        "eta_source": profile.eta_source,
        "calculation_version": profile.calculation_version,
        "recalculated_at": profile.targets_recalculated_at,
    }


def update_account(session: Session, user_id: str, data: AccountUpdate) -> User:
    user = get_user(session, user_id)
    user.name = data.name
    user.email = str(data.email).lower()
    user.timezone = data.timezone
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, detail="Bu e-posta zaten kayıtlı.") from exc
    session.refresh(user)
    return user
