from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.models.user import User
from app.routes.dependencies import Database, require_current_user, verify_csrf
from app.schemas.activity import ActivityToday, DailyStepsRead, DailyStepsWrite, WorkoutRead, WorkoutWrite
from app.schemas.food import CustomFoodCreate, ExternalCacheRequest, ExternalFoodCandidate, FoodLogCreate, FoodLogPreview, FoodLogPreviewRequest, FoodRead, FoodSearchResponse
from app.schemas.nutrition import MealRead
from app.services import activity, food_data, nutrition
from app.services.food_providers.open_food_facts import OpenFoodFactsProvider

router = APIRouter(prefix="/me", tags=["food-data", "activity"])
CurrentUser = Annotated[User, Depends(require_current_user)]
CSRF = Depends(verify_csrf)


def _food_read(food):
    return FoodRead.model_validate(food)


@router.get("/foods/search", response_model=FoodSearchResponse)
def search_foods(request: Request, user: CurrentUser, session: Database, q: str = Query(min_length=2, max_length=120), include_external: bool = False):
    local = food_data.search_foods(session, user.id, q)
    external = []
    if include_external and len(local) < 5:
        settings = request.app.state.settings
        provider = OpenFoodFactsProvider(settings.open_food_facts_user_agent, settings.food_provider_timeout_seconds)
        try:
            for item in provider.search(q):
                complete = all(item.get(k) is not None for k in food_data.REQUIRED)
                external.append(ExternalFoodCandidate(source="open_food_facts", source_food_id=item["source_food_id"], canonical_name=item["canonical_name"], brand=item["brand"], barcode=item["barcode"], country=item["country"], basis_type=item["basis_type"], calories=item["calories"], protein_g=item["protein_g"], carbs_g=item["carbs_g"], fat_g=item["fat_g"], has_complete_nutrition=complete))
        except Exception as exc:
            raise HTTPException(503, f"Open Food Facts şu anda kullanılamıyor ({type(exc).__name__}).") from exc
    return {"local": [_food_read(f) for f in local], "external": external}


@router.post("/foods/external-cache", response_model=FoodRead, dependencies=[CSRF])
def cache_external(data: ExternalCacheRequest, request: Request, user: CurrentUser, session: Database):
    settings = request.app.state.settings
    provider = OpenFoodFactsProvider(settings.open_food_facts_user_agent, settings.food_provider_timeout_seconds)
    try:
        normalized = provider.detail(data.source_food_id)
        return _food_read(food_data.upsert_external_food(session, normalized))
    except (ValueError, LookupError) as exc: raise HTTPException(422, str(exc)) from exc
    except Exception as exc: raise HTTPException(503, f"Open Food Facts şu anda kullanılamıyor ({type(exc).__name__}).") from exc


@router.post("/foods", response_model=FoodRead, status_code=201, dependencies=[CSRF])
def create_custom_food(data: CustomFoodCreate, user: CurrentUser, session: Database):
    return _food_read(food_data.create_custom_food(session, user.id, data))


@router.get("/foods/recent", response_model=list[FoodRead])
def recent_foods(user: CurrentUser, session: Database): return [_food_read(f) for f in food_data.recent_foods(session, user.id)]


@router.get("/foods/favorites", response_model=list[FoodRead])
def favorite_foods(user: CurrentUser, session: Database): return [_food_read(f) for f in food_data.favorite_foods(session, user.id)]


@router.put("/foods/{food_id}/favorite", status_code=204, dependencies=[CSRF])
def favorite(food_id: UUID, user: CurrentUser, session: Database): food_data.set_favorite(session, user.id, str(food_id)); return Response(status_code=204)


@router.delete("/foods/{food_id}/favorite", status_code=204, dependencies=[CSRF])
def unfavorite(food_id: UUID, user: CurrentUser, session: Database): food_data.remove_favorite(session, user.id, str(food_id)); return Response(status_code=204)


@router.post("/foods/log-preview", response_model=FoodLogPreview)
def preview(data: FoodLogPreviewRequest, user: CurrentUser, session: Database): return food_data.preview_food(session, user.id, data)


@router.post("/foods/log", response_model=MealRead, status_code=201, dependencies=[CSRF])
def log(data: FoodLogCreate, user: CurrentUser, session: Database): return nutrition.meal_read(food_data.log_food(session, user.id, data))


@router.put("/daily-steps", response_model=DailyStepsRead, dependencies=[CSRF])
def put_steps(data: DailyStepsWrite, user: CurrentUser, session: Database): return activity.upsert_steps(session, user.id, data)


@router.get("/daily-steps", response_model=list[DailyStepsRead])
def get_steps(user: CurrentUser, session: Database, start: date | None = None, end: date | None = None): return activity.list_steps(session, user.id, start, end)


@router.delete("/daily-steps/{row_id}", status_code=204, dependencies=[CSRF])
def remove_steps(row_id: UUID, user: CurrentUser, session: Database): activity.delete_steps(session, user.id, str(row_id)); return Response(status_code=204)


@router.post("/workouts", response_model=WorkoutRead, status_code=201, dependencies=[CSRF])
def post_workout(data: WorkoutWrite, user: CurrentUser, session: Database): return activity.create_workout(session, user.id, data)


@router.get("/workouts", response_model=list[WorkoutRead])
def get_workouts(user: CurrentUser, session: Database, day: date | None = None): return activity.list_workouts(session, user.id, user, day)


@router.put("/workouts/{workout_id}", response_model=WorkoutRead, dependencies=[CSRF])
def put_workout(workout_id: UUID, data: WorkoutWrite, user: CurrentUser, session: Database): return activity.replace_workout(session, user.id, str(workout_id), data)


@router.delete("/workouts/{workout_id}", status_code=204, dependencies=[CSRF])
def remove_workout(workout_id: UUID, user: CurrentUser, session: Database): activity.delete_workout(session, user.id, str(workout_id)); return Response(status_code=204)


@router.get("/activity/today", response_model=ActivityToday)
def get_activity_today(user: CurrentUser, session: Database): return activity.today_summary(session, user)
