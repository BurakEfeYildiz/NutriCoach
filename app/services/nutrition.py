from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.models.nutrition import Meal, MealItem, NUTRIENTS
from app.models.user import User, utc_now
from app.schemas.nutrition import DaySummary, ItemRead, MealRead, MealReplace, MealWrite, Totals, WeekSummary
from app.services.users import get_user


def local_date(user: User, now: datetime | None = None) -> date:
    now = now or utc_now()
    if now.tzinfo is None:
        raise ValueError('Saat dilimi zorunlu.')
    return now.astimezone(ZoneInfo(user.timezone)).date()


def day_bounds(day: date, timezone_name: str) -> tuple[datetime, datetime]:
    zone = ZoneInfo(timezone_name)
    # Construct both local midnights independently: DST days need not be 24 hours.
    return (
        datetime.combine(day, time.min, zone).astimezone(timezone.utc),
        datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc),
    )


def meal_totals(meal: Meal) -> Totals:
    return Totals(**{key: sum((getattr(item, key) for item in meal.items), Decimal('0.00')) for key in NUTRIENTS})


def meal_read(meal: Meal) -> MealRead:
    return MealRead(**{
        **MealWrite.model_validate(meal).model_dump(),
        'id': meal.id, 'user_id': meal.user_id, 'version': meal.version,
        'created_at': meal.created_at, 'updated_at': meal.updated_at,
        'items': [ItemRead.model_validate(item) for item in meal.items],
        'totals': meal_totals(meal),
    })


def owned_meal(session: Session, user_id: str, meal_id: str) -> Meal:
    meal = session.scalar(select(Meal).where(Meal.user_id == user_id, Meal.id == meal_id).options(selectinload(Meal.items)))
    if meal is None:
        raise HTTPException(404, 'Öğün bulunamadı.')
    return meal


def commit_meal(session: Session, *, commit: bool = True) -> None:
    try:
        session.commit() if commit else session.flush()
    except StaleDataError:
        session.rollback()
        raise HTTPException(409, 'Öğün değişti; güncel kaydı alıp yeniden deneyin.')


def create_meal(session: Session, user_id: str, data: MealWrite, *, commit: bool = True) -> Meal:
    get_user(session, user_id)
    meal = Meal(user_id=user_id, **data.model_dump(exclude={'items'}))
    meal.items = [MealItem(user_id=user_id, **item.model_dump()) for item in data.items]
    session.add(meal)
    commit_meal(session, commit=commit)
    session.refresh(meal)
    return meal


def replace_meal(session: Session, user_id: str, meal_id: str, data: MealReplace, *, commit: bool = True) -> Meal:
    meal = owned_meal(session, user_id, meal_id)
    if meal.version != data.expected_version:
        raise HTTPException(409, 'Öğün sürümü güncel değil.')
    for key, value in data.model_dump(exclude={'items', 'expected_version'}).items():
        setattr(meal, key, value)
    meal.items = [MealItem(user_id=user_id, **item.model_dump()) for item in data.items]
    meal.updated_at = utc_now()  # Item-only edits must also update/check the parent version.
    commit_meal(session, commit=commit)
    session.refresh(meal)
    return meal


def delete_meal(session: Session, user_id: str, meal_id: str, *, commit: bool = True) -> None:
    session.delete(owned_meal(session, user_id, meal_id))
    commit_meal(session, commit=commit)


def list_meals(session: Session, user_id: str, day: date | None = None, limit: int = 100, offset: int = 0) -> list[Meal]:
    user = get_user(session, user_id)
    query = select(Meal).where(Meal.user_id == user_id).options(selectinload(Meal.items))
    if day:
        start, end = day_bounds(day, user.timezone)
        query = query.where(Meal.occurred_at >= start, Meal.occurred_at < end)
    return list(session.scalars(query.order_by(Meal.occurred_at.desc(), Meal.id).limit(limit).offset(offset)))


def range_meals(session: Session, user: User, start_day: date, end_day: date) -> list[Meal]:
    start, _ = day_bounds(start_day, user.timezone)
    _, end = day_bounds(end_day, user.timezone)
    return list(session.scalars(select(Meal).where(
        Meal.user_id == user.id, Meal.occurred_at >= start, Meal.occurred_at < end
    ).options(selectinload(Meal.items)).order_by(Meal.occurred_at, Meal.id)))


def summarize_day(user: User, day: date, meals: list[Meal]) -> DaySummary:
    per_meal = [meal_totals(meal) for meal in meals]
    totals = Totals(**{key: sum((getattr(total, key) for total in per_meal), Decimal('0.00')) for key in NUTRIENTS}) if meals else None
    targets = ('calorie_target', 'protein_target_g', 'carb_target_g', 'fat_target_g')
    remaining = {}
    for nutrient, field in zip(NUTRIENTS, targets):
        target = getattr(user.profile, field)
        remaining[nutrient] = Decimal(str(target)) - getattr(totals, nutrient) if target is not None and totals else None
    return DaySummary(date=day, timezone=user.timezone, meal_count=len(meals), has_records=bool(meals), totals=totals, remaining_by_target=remaining)


def daily_summary(session: Session, user_id: str, day: date | None = None, now: datetime | None = None) -> DaySummary:
    user = get_user(session, user_id)
    day = day or local_date(user, now)
    return summarize_day(user, day, range_meals(session, user, day, day))


def weekly_summary(session: Session, user_id: str, end_day: date | None = None, now: datetime | None = None) -> WeekSummary:
    user = get_user(session, user_id)
    end_day = end_day or local_date(user, now)
    start_day = end_day - timedelta(days=6)
    grouped = {start_day + timedelta(days=i): [] for i in range(7)}
    for meal in range_meals(session, user, start_day, end_day):
        grouped[meal.occurred_at.astimezone(ZoneInfo(user.timezone)).date()].append(meal)
    days = [summarize_day(user, day, meals) for day, meals in grouped.items()]
    recorded = [day.totals for day in days if day.has_records]
    average = Totals(**{
        key: (sum((getattr(total, key) for total in recorded), Decimal('0.00')) / len(recorded)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        for key in NUTRIENTS
    }) if recorded else None
    target = user.profile.calorie_target
    return WeekSummary(
        start_date=start_day, end_date=end_day, timezone=user.timezone,
        recorded_days=len(recorded), missing_days=7-len(recorded),
        average_over_recorded_days=average,
        days_above_current_calorie_target=sum(total.calories > target for total in recorded) if target is not None else None,
        days_below_current_calorie_target=sum(total.calories < target for total in recorded) if target is not None else None,
        days=days,
    )
