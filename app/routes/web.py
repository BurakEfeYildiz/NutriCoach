from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User, UserProfile
from app.routes.dependencies import (
    Database,
    get_csrf_token_for_session,
    get_current_user_optional,
    get_session,
    get_settings,
)
from app.schemas.user import UserRead
from app.services import auth_service, users

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES_DIR = ROOT / "app" / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["web"])


def _render_authenticated(
    request: Request,
    session: Session,
    template_name: str,
    active_tab: str,
    *,
    require_onboarding: bool = True,
):
    user = get_current_user_optional(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if require_onboarding and not users.onboarding_complete(session, user.id):
        return RedirectResponse(url="/onboarding", status_code=status.HTTP_303_SEE_OTHER)

    settings = get_settings(request)
    auth_session = getattr(request.state, "auth_session", None)
    csrf_token = get_csrf_token_for_session(auth_session, settings) if auth_session else ""

    return templates.TemplateResponse(
        request,
        template_name,
        {
            "active_tab": active_tab,
            "user": user,
            "csrf_token": csrf_token,
        },
    )


@router.get("/", response_class=RedirectResponse, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
def root(request: Request, session: Database):
    user = get_current_user_optional(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    destination = "/today" if users.onboarding_complete(session, user.id) else "/onboarding"
    return RedirectResponse(url=destination, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/today", response_class=HTMLResponse)
def today_page(request: Request, session: Database):
    return _render_authenticated(request, session, "dashboard.html", "today")


@router.get("/coach", response_class=HTMLResponse)
def coach_page(request: Request, session: Database):
    return _render_authenticated(request, session, "coach.html", "coach")


@router.get("/meals", response_class=HTMLResponse)
def meals_page(request: Request, session: Database):
    return _render_authenticated(request, session, "meals.html", "meals")


@router.get("/progress", response_class=HTMLResponse)
def progress_page(request: Request, session: Database):
    return _render_authenticated(request, session, "progress.html", "progress")


@router.get("/recipes", response_class=HTMLResponse)
def recipes_page(request: Request, session: Database):
    return _render_authenticated(request, session, "recipes.html", "recipes")


@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, session: Database):
    return _render_authenticated(request, session, "profile.html", "profile")


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, session: Database):
    return _render_authenticated(request, session, "account.html", "account", require_onboarding=False)


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_page(request: Request, session: Database):
    user = get_current_user_optional(request, session)
    if user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    if users.onboarding_complete(session, user.id):
        return RedirectResponse(url="/today", status_code=status.HTTP_303_SEE_OTHER)
    return _render_authenticated(request, session, "onboarding.html", "onboarding", require_onboarding=False)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, session: Database):
    user = get_current_user_optional(request, session)
    if user is not None:
        destination = "/today" if users.onboarding_complete(session, user.id) else "/onboarding"
        return RedirectResponse(url=destination, status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, session: Database):
    user = get_current_user_optional(request, session)
    if user is not None:
        destination = "/today" if users.onboarding_complete(session, user.id) else "/onboarding"
        return RedirectResponse(url=destination, status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "register.html", {})


@router.get("/logout", response_class=RedirectResponse)
def logout_page(request: Request, response: Response, session: Database):
    settings = get_settings(request)
    raw_token = request.cookies.get(settings.session_cookie_name)
    if raw_token:
        auth_service.revoke_session(session, raw_token)

    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.is_cookie_secure,
    )
    return redirect


@router.get("/api/v1/dev/bootstrap", response_model=UserRead, tags=["users (local development)"])
def dev_bootstrap(request: Request, session: Database):
    """Local development helper: guarded by enable_dev_bootstrap setting."""
    settings = get_settings(request)
    if not settings.enable_dev_bootstrap:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Geliştirme kullanıcısı oluşturucu devre dışı.",
        )

    user = session.scalars(select(User).order_by(User.created_at.asc()).limit(1)).first()
    if user is None:
        user = User(name="Burak", timezone="Europe/Istanbul", profile=UserProfile(calorie_target=2200))
        session.add(user)
        session.commit()
        session.refresh(user)
    return user
