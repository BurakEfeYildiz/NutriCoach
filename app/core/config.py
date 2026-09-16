from decimal import Decimal
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NUTRICOACH_", env_file=".env", env_file_encoding="utf-8", extra="ignore", populate_by_name=True
    )
    app_name: str = "NutriCoach"
    database_url: str = Field(default="sqlite:///./nutricoach.db", validation_alias=AliasChoices('DATABASE_URL', 'NUTRICOACH_DATABASE_URL'))
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

    app_environment: Literal['development', 'local', 'test', 'production'] = Field(
        default='local', validation_alias=AliasChoices('APP_ENV', 'NUTRICOACH_APP_ENVIRONMENT')
    )
    gemini_diagnostics: bool = False
    usda_fdc_api_key: SecretStr | None = Field(default=None, validation_alias=AliasChoices('USDA_FDC_API_KEY', 'NUTRICOACH_USDA_FDC_API_KEY'))
    open_food_facts_user_agent: str = Field(default="NutriCoach/0.9 (local development)", validation_alias=AliasChoices('OPEN_FOOD_FACTS_USER_AGENT', 'NUTRICOACH_OPEN_FOOD_FACTS_USER_AGENT'))
    food_provider_timeout_seconds: int = Field(default=15, ge=1, le=60)

    secret_key: SecretStr = Field(default=SecretStr("nutricoach-insecure-dev-secret-change-in-prod"), validation_alias=AliasChoices("SECRET_KEY", "NUTRICOACH_SECRET_KEY"))
    session_cookie_name: str = "nutricoach_session"
    session_ttl_days: int = Field(default=30, ge=1, le=365)
    session_cookie_secure: bool | None = None
    enable_dev_bootstrap: bool = False
    allow_unauthenticated_legacy: bool = False
    csrf_secret: SecretStr = Field(default=SecretStr("nutricoach-csrf-dev-secret"), validation_alias=AliasChoices("CSRF_SECRET", "NUTRICOACH_CSRF_SECRET"))

    port: int = Field(default=8080, validation_alias=AliasChoices('PORT', 'NUTRICOACH_PORT'))
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver"],
        validation_alias=AliasChoices('ALLOWED_HOSTS', 'NUTRICOACH_ALLOWED_HOSTS'),
    )
    allow_sqlite_in_production: bool = False

    @field_validator('allowed_hosts', mode='before')
    @classmethod
    def parse_allowed_hosts(cls, v):
        if isinstance(v, str):
            return [h.strip() for h in v.split(",") if h.strip()]
        return v

    @model_validator(mode='after')
    def validate_production_settings(self) -> 'Settings':
        if self.app_environment == 'production':
            insecure_secret_values = {
                "nutricoach-insecure-dev-secret-change-in-prod",
                "nutricoach-development-secret-change-in-production-min-32-chars",
            }
            secret_val = self.secret_key.get_secret_value() if self.secret_key else ""
            if not secret_val or secret_val in insecure_secret_values or len(secret_val) < 32:
                raise ValueError("In production, SECRET_KEY must be set to a secure, non-default value (min 32 characters).")

            insecure_csrf_values = {
                "nutricoach-csrf-dev-secret",
                "nutricoach-csrf-development-secret-change-in-prod-32-chars",
            }
            csrf_val = self.csrf_secret.get_secret_value() if self.csrf_secret else ""
            if not csrf_val or csrf_val in insecure_csrf_values or len(csrf_val) < 32:
                raise ValueError("In production, CSRF_SECRET must be set to a secure, non-default value (min 32 characters).")

            if self.database_url.startswith("sqlite") and not self.allow_sqlite_in_production:
                raise ValueError("In production, SQLite is not supported. PostgreSQL DATABASE_URL is required.")

            if self.enable_dev_bootstrap:
                raise ValueError("enable_dev_bootstrap must be False in production.")
            if self.allow_unauthenticated_legacy:
                raise ValueError("allow_unauthenticated_legacy must be False in production.")

        return self

    @property
    def is_cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_environment == "production"
