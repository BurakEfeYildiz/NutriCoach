from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.core.config import Settings
from app.db.database import create_database
from app.db.migrate import require_current_schema
from app.routes import chat, health, nutrition, users
from app.services.chat_service import ChatService
from app.services.gemini_service import GeminiProvider, GoogleGeminiProvider


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

    application = FastAPI(title=settings.app_name, version="0.3.0", lifespan=lifespan)
    application.state.session_factory = session_factory
    application.state.chat_service = ChatService(session_factory, provider or GoogleGeminiProvider(settings), settings)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    application.include_router(health.router)
    application.include_router(users.router, prefix="/api/v1")
    application.include_router(nutrition.router, prefix="/api/v1")
    application.include_router(chat.router, prefix="/api/v1")
    return application


app = create_app()
