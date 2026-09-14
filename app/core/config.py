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

    app_environment: Literal['local', 'production'] = 'production'
    gemini_diagnostics: bool = False
