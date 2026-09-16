from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.activity import DailySteps, Workout
from app.models.user import User
from app.schemas.activity import ActivityToday, DailyStepsWrite, WorkoutWrite
from app.services.nutrition import day_bounds, local_date
from app.services.weights import current_weight

MET_VALUES = {
    "walking": {"light": "2.8", "moderate": "3.5", "vigorous": "5.0"},
    "running": {"light": "6.0", "moderate": "8.3", "vigorous": "11.0"},
    "cycling": {"light": "4.0", "moderate": "6.8", "vigorous": "10.0"},
    "strength": {"light": "3.0", "moderate": "5.0", "vigorous": "6.0"},
    "swimming": {"light": "4.8", "moderate": "6.0", "vigorous": "9.8"},
    "yoga": {"light": "2.0", "moderate": "2.5", "vigorous": "4.0"},
}


def upsert_steps(session: Session, user_id: str, data: DailyStepsWrite) -> DailySteps:
    row = session.scalar(select(DailySteps).where(DailySteps.user_id == user_id, DailySteps.day == data.day, DailySteps.source == data.source))
    if row is None:
        row = DailySteps(user_id=user_id, **data.model_dump()); session.add(row)
    else:
        row.step_count = data.step_count
    session.commit(); session.refresh(row); return row


def list_steps(session: Session, user_id: str, start: date | None = None, end: date | None = None) -> list[DailySteps]:
    stmt = select(DailySteps).where(DailySteps.user_id == user_id)
    if start: stmt = stmt.where(DailySteps.day >= start)
    if end: stmt = stmt.where(DailySteps.day <= end)
    return list(session.scalars(stmt.order_by(DailySteps.day.desc(), DailySteps.source)))


def delete_steps(session: Session, user_id: str, row_id: str) -> None:
    row = session.scalar(select(DailySteps).where(DailySteps.id == row_id, DailySteps.user_id == user_id))
    if not row: raise HTTPException(404, "Adım kaydı bulunamadı.")
    session.delete(row); session.commit()


def _estimate(session: Session, user_id: str, data: WorkoutWrite) -> tuple[Decimal | None, Decimal | None, str | None]:
    met_raw = MET_VALUES.get(data.activity_type, {}).get(data.intensity)
    weight = current_weight(session, user_id)
    if not met_raw or not weight:
        return None, None, None
    met = Decimal(met_raw)
    calories = (met * Decimal("3.5") * weight.weight_kg / Decimal("200") * data.duration_minutes).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    return met.quantize(Decimal(".01")), calories, "met_estimate"


def create_workout(session: Session, user_id: str, data: WorkoutWrite) -> Workout:
    met, calories, estimate_source = _estimate(session, user_id, data)
    row = Workout(user_id=user_id, met_value=met, estimated_calories=calories, calorie_estimate_source=estimate_source, **data.model_dump())
    session.add(row); session.commit(); session.refresh(row); return row


def owned_workout(session: Session, user_id: str, workout_id: str) -> Workout:
    row = session.scalar(select(Workout).where(Workout.id == workout_id, Workout.user_id == user_id))
    if not row: raise HTTPException(404, "Egzersiz kaydı bulunamadı.")
    return row


def replace_workout(session: Session, user_id: str, workout_id: str, data: WorkoutWrite) -> Workout:
    row = owned_workout(session, user_id, workout_id)
    for key, value in data.model_dump().items(): setattr(row, key, value)
    row.met_value, row.estimated_calories, row.calorie_estimate_source = _estimate(session, user_id, data)
    session.commit(); session.refresh(row); return row


def delete_workout(session: Session, user_id: str, workout_id: str) -> None:
    session.delete(owned_workout(session, user_id, workout_id)); session.commit()


def list_workouts(session: Session, user_id: str, user: User, day: date | None = None, limit: int = 100) -> list[Workout]:
    stmt = select(Workout).where(Workout.user_id == user_id)
    if day:
        start, end = day_bounds(day, user.timezone)
        stmt = stmt.where(Workout.occurred_at >= start, Workout.occurred_at < end)
    return list(session.scalars(stmt.order_by(Workout.occurred_at.desc()).limit(limit)))


def today_summary(session: Session, user: User, now=None) -> ActivityToday:
    day = local_date(user, now)
    steps = list_steps(session, user.id, day, day)
    workouts = list_workouts(session, user.id, user, day)
    calories = [w.estimated_calories for w in workouts if w.estimated_calories is not None]
    return ActivityToday(date=day, timezone=user.timezone, steps=steps,
        total_steps=sum(s.step_count for s in steps) if steps else None,
        workouts=workouts, total_workout_minutes=sum(w.duration_minutes for w in workouts),
        estimated_activity_calories=sum(calories, Decimal("0.00")) if calories else None)
