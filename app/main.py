from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path
import time

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings
from app.db.database import create_database
from app.db.migrate import require_current_schema
from app.routes import auth, chat, health, me, memories, nutrition, users, web
from app.services.chat_service import ChatService
from app.services.gemini_service import GeminiProvider, GoogleGeminiProvider

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "app" / "static"


def create_app(settings: Settings | None = None, *, provider: GeminiProvider | None = None) -> FastAPI:
    settings = settings or Settings()
    engine, session_factory = create_database(settings.database_url)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            require_current_schema(engine)
            yield
        finally:
            engine.dispose()

    application = FastAPI(title=settings.app_name, version="0.8.0", lifespan=lifespan)
    application.state.settings = settings
    application.state.session_factory = session_factory
    gemini_provider = provider or GoogleGeminiProvider(settings)
    application.state.provider = gemini_provider
    application.state.chat_service = ChatService(session_factory, gemini_provider, settings)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    # Basic in-memory rate limiter for auth mutations (login/register)
    auth_request_history: dict[str, list[float]] = defaultdict(list)
    application.state.auth_request_history = auth_request_history
    RATE_LIMIT_WINDOW = 60.0  # seconds
    RATE_LIMIT_MAX_REQUESTS = 10  # max requests per window

    @application.middleware("http")
    async def rate_limit_auth_endpoints(request: Request, call_next):
        if request.method == "POST" and request.url.path in ("/api/v1/auth/login", "/api/v1/auth/register"):
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or (request.client.host if request.client else "unknown")
            )
            now = time.monotonic()
            window_start = now - RATE_LIMIT_WINDOW
            timestamps = [t for t in auth_request_history[client_ip] if t > window_start]
            if len(timestamps) >= RATE_LIMIT_MAX_REQUESTS:
                auth_request_history[client_ip] = timestamps
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Çok fazla deneme yapıldı. Lütfen 1 dakika sonra tekrar deneyin."},
                    headers={"Retry-After": "60"},
                )
            timestamps.append(now)
            auth_request_history[client_ip] = timestamps

        return await call_next(request)

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Static assets and Web UI routes
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    application.include_router(web.router)

    # API endpoints
    application.include_router(health.router)
    application.include_router(auth.router, prefix="/api/v1")
    application.include_router(me.router, prefix="/api/v1")
    application.include_router(users.router, prefix="/api/v1")
    application.include_router(nutrition.router, prefix="/api/v1")
    application.include_router(chat.router, prefix="/api/v1")
    application.include_router(memories.router, prefix="/api/v1")
    return application


app = create_app()
