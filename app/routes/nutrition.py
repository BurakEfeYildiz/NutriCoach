from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.routes.users import Database
from app.schemas.nutrition import DaySummary, MealRead, MealReplace, MealWrite, WeekSummary, WeightRead, WeightWrite
from app.services import nutrition, weights
from app.services.users import get_user

router = APIRouter(prefix='/users/{user_id}', tags=['nutrition (local development)'])
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]


@router.post('/meals', response_model=MealRead, status_code=201)
def create_meal(user_id: UUID, data: MealWrite, session: Database):
    return nutrition.meal_read(nutrition.create_meal(session, str(user_id), data))


@router.get('/meals', response_model=list[MealRead])
def list_meals(user_id: UUID, session: Database, day: date | None = None, limit: Limit = 100, offset: Offset = 0):
    return [nutrition.meal_read(meal) for meal in nutrition.list_meals(session, str(user_id), day, limit, offset)]


@router.get('/meals/today', response_model=list[MealRead])
def today_meals(user_id: UUID, session: Database, limit: Limit = 100, offset: Offset = 0):
    user = get_user(session, str(user_id))
    return [nutrition.meal_read(meal) for meal in nutrition.list_meals(session, user.id, nutrition.local_date(user), limit, offset)]


@router.get('/meals/{meal_id}', response_model=MealRead)
def get_meal(user_id: UUID, meal_id: UUID, session: Database):
    return nutrition.meal_read(nutrition.owned_meal(session, str(user_id), str(meal_id)))


@router.put('/meals/{meal_id}', response_model=MealRead)
def replace_meal(user_id: UUID, meal_id: UUID, data: MealReplace, session: Database):
    """Öğünü ve item listesini atomik olarak tamamen değiştirir; item kimlikleri yenilenir."""
    return nutrition.meal_read(nutrition.replace_meal(session, str(user_id), str(meal_id), data))


@router.delete('/meals/{meal_id}', status_code=204)
def delete_meal(user_id: UUID, meal_id: UUID, session: Database):
    nutrition.delete_meal(session, str(user_id), str(meal_id))
    return Response(status_code=204)


@router.get('/nutrition/daily', response_model=DaySummary)
def daily(user_id: UUID, session: Database, day: date | None = None):
    return nutrition.daily_summary(session, str(user_id), day)


@router.get('/nutrition/weekly', response_model=WeekSummary)
def weekly(user_id: UUID, session: Database, end_day: date | None = None):
    """Bitiş günü dahil son 7 yerel takvim günü; varsayılan bitiş bugün."""
    return nutrition.weekly_summary(session, str(user_id), end_day)


@router.post('/weight-logs', response_model=WeightRead, status_code=201)
def create_weight(user_id: UUID, data: WeightWrite, session: Database):
    return weights.create_weight(session, str(user_id), data)


@router.get('/weight-logs', response_model=list[WeightRead])
def list_weights(user_id: UUID, session: Database, limit: Limit = 100, offset: Offset = 0):
    return weights.list_weights(session, str(user_id), limit, offset)


@router.get('/weight-logs/current', response_model=WeightRead | None)
def current_weight(user_id: UUID, session: Database):
    return weights.current_weight(session, str(user_id))


@router.get('/weight-logs/{weight_id}', response_model=WeightRead)
def get_weight(user_id: UUID, weight_id: UUID, session: Database):
    return weights.owned_weight(session, str(user_id), str(weight_id))


@router.put('/weight-logs/{weight_id}', response_model=WeightRead)
def replace_weight(user_id: UUID, weight_id: UUID, data: WeightWrite, session: Database):
    return weights.replace_weight(session, str(user_id), str(weight_id), data)


@router.delete('/weight-logs/{weight_id}', status_code=204)
def delete_weight(user_id: UUID, weight_id: UUID, session: Database):
    weights.delete_weight(session, str(user_id), str(weight_id))
    return Response(status_code=204)
