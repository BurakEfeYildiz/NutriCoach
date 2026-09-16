"""Authenticated, read-oriented adaptive metrics and structured recipes."""
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.models.user import User
from app.routes.dependencies import Database, require_current_user, verify_csrf
from app.schemas.analytics import AdaptiveDashboard, ExpenditureEstimate, Gamification, InsightCandidate, WeightTrend, WeeklyReview
from app.schemas.recipe import DietaryExclusions, RecipeCreate, RecipeRead
from app.services import adaptive_analytics, recipes

router = APIRouter(prefix="/me", tags=["adaptive-coach", "recipes"])
CurrentUser = Annotated[User, Depends(require_current_user)]
CSRF = Depends(verify_csrf)


@router.get("/adaptive-dashboard", response_model=AdaptiveDashboard)
def dashboard(user: CurrentUser, session: Database):
    return adaptive_analytics.build_dashboard(session, user.id)


@router.get("/weight-trend", response_model=WeightTrend)
def trend(user: CurrentUser, session: Database):
    return adaptive_analytics.build_dashboard(session, user.id).weight


@router.get("/expenditure-estimate", response_model=ExpenditureEstimate)
def expenditure(user: CurrentUser, session: Database):
    return adaptive_analytics.build_dashboard(session, user.id).expenditure


@router.get("/daily-insights", response_model=list[InsightCandidate])
def insights(user: CurrentUser, session: Database):
    return adaptive_analytics.build_dashboard(session, user.id).insights


@router.get("/weekly-review", response_model=WeeklyReview)
def weekly_review(user: CurrentUser, session: Database):
    return adaptive_analytics.build_dashboard(session, user.id).weekly_review


@router.get("/consistency", response_model=Gamification)
def consistency(user: CurrentUser, session: Database):
    return adaptive_analytics.build_dashboard(session, user.id).gamification


@router.get("/recipes/recommended", response_model=list[RecipeRead])
def recommended(user: CurrentUser, session: Database, meal_type: str | None = None):
    return recipes.recommend(session, user.id, meal_type=meal_type)


@router.get("/recipes/{recipe_id}", response_model=RecipeRead)
def recipe_detail(recipe_id: UUID, user: CurrentUser, session: Database):
    return recipes.recipe_read(session, user.id, recipes.owned_recipe(session, user.id, str(recipe_id)))


@router.post("/recipes", response_model=RecipeRead, status_code=201, dependencies=[CSRF])
def create_recipe(data: RecipeCreate, user: CurrentUser, session: Database):
    return recipes.recipe_read(session, user.id, recipes.create_recipe(session, user.id, data))


@router.get("/dietary-exclusions", response_model=DietaryExclusions)
def get_exclusions(user: CurrentUser):
    return DietaryExclusions(foods=user.profile.dietary_exclusions or [])


@router.put("/dietary-exclusions", response_model=DietaryExclusions, dependencies=[CSRF])
def put_exclusions(data: DietaryExclusions, user: CurrentUser, session: Database):
    return recipes.set_exclusions(session, user.id, data)
