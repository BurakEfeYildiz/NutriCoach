from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NUTRICOACH_", env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )
    app_name: str = "NutriCoach"
    database_url: str = "sqlite:///./nutricoach.db"
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices('GEMINI_API_KEY', 'NUTRICOACH_GEMINI_API_KEY'))
    gemini_model: str = Field(default='', max_length=200, validation_alias=AliasChoices('GEMINI_MODEL', 'NUTRICOACH_GEMINI_MODEL'))
    gemini_timeout_seconds: int = Field(default=30, ge=1, le=120)
    chat_recent_messages: int = Field(default=10, ge=0, le=20)
    chat_history_chars: int = Field(default=8000, ge=0, le=20000)
    context_max_today_meals: int = Field(default=15, ge=1, le=50)
    context_max_weight_logs: int = Field(default=10, ge=1, le=50)
    context_max_chars: int = Field(default=16000, ge=1000, le=64000)
    context_max_memories: int = Field(default=10, ge=1, le=50)
    memory_min_confidence: Decimal = Field(default=Decimal('0.60'), ge=0, le=1)

    app_environment: Literal['local', 'production'] = Field(default='local', validation_alias=AliasChoices('APP_ENV', 'NUTRICOACH_APP_ENVIRONMENT'))
    gemini_diagnostics: bool = False

    secret_key: SecretStr = Field(default=SecretStr("nutricoach-insecure-dev-secret-change-in-prod"), validation_alias=AliasChoices("SECRET_KEY", "NUTRICOACH_SECRET_KEY"))
    session_cookie_name: str = "nutricoach_session"
    session_ttl_days: int = Field(default=30, ge=1, le=365)
    session_cookie_secure: bool | None = None
    enable_dev_bootstrap: bool = False
    allow_unauthenticated_legacy: bool = False
    csrf_secret: SecretStr = Field(default=SecretStr("nutricoach-csrf-dev-secret"), validation_alias=AliasChoices("CSRF_SECRET", "NUTRICOACH_CSRF_SECRET"))

    @property
    def is_cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_environment == "production"
