from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from .schemas import ProviderId


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="LONORA_", extra="ignore", case_sensitive=False
    )

    database_url: str
    jwt_secret: SecretStr = Field(min_length=32)
    auth_token_ttl_seconds: int = Field(default=86_400, ge=300, le=2_592_000)
    model_provider: ProviderId = "xai"
    model_name: str = "grok-4.20-0309-non-reasoning"
    model_api_key: SecretStr | None = None
    worker_poll_seconds: float = 0.5
    run_lease_seconds: int = 150


@lru_cache
def get_settings() -> Settings:
    return Settings()
