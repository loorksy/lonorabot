from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="LONORA_", extra="ignore")
    database_url: str
    encryption_key: SecretStr
    bootstrap_token: SecretStr = Field(min_length=24)
    session_seconds: int = Field(default=86400, ge=300, le=2592000)
    cookie_secure: bool = True
    allowed_origin: str = "http://localhost:8000"
    artifact_root: Path = Path(".runtime/artifacts")
    worker_poll_seconds: float = Field(default=0.5, ge=0.1)
    run_lease_seconds: int = Field(default=120, ge=30)
    maximum_tool_rounds: int = Field(default=24, ge=1, le=100)
    maximum_subagents: int = Field(default=4, ge=1, le=12)
    livekit_url: str = "ws://localhost:7880"
    livekit_internal_url: str = "ws://localhost:7880"
    livekit_api_key: str | None = None
    livekit_api_secret: SecretStr | None = None
    webhook_secret: SecretStr | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
