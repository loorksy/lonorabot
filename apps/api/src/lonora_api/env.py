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
    web_root: Path = Path("apps/web/dist")
    artifact_root: Path = Path(".runtime/artifacts")
    android_apk_path: Path = Path(".runtime/releases/android/lonora.apk")
    worker_poll_seconds: float = Field(default=0.5, ge=0.1)
    run_lease_seconds: int = Field(default=120, ge=30)
    maximum_tool_rounds: int = Field(default=24, ge=1, le=100)
    maximum_subagents: int = Field(default=4, ge=1, le=12)
    webhook_secret: SecretStr | None = None
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # pyright: ignore[reportCallIssue] -- BaseSettings reads required fields from environment.
