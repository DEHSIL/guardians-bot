from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field, RedisDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or a local .env file."""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: SecretStr = Field(validation_alias="BOT_TOKEN")
    redis_url: RedisDsn = Field(validation_alias="REDIS_URL")
    backend_base_url: AnyHttpUrl = Field(validation_alias="BACKEND_BASE_URL")
    backend_api_token: SecretStr = Field(min_length=1, validation_alias="BACKEND_API_TOKEN")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    request_timeout_seconds: float = Field(default=10.0, gt=0, validation_alias="REQUEST_TIMEOUT_SECONDS")
    rate_limit_requests: int = Field(default=5, ge=1, validation_alias="RATE_LIMIT_REQUESTS")
    rate_limit_window_seconds: int = Field(default=10, ge=1, validation_alias="RATE_LIMIT_WINDOW_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
