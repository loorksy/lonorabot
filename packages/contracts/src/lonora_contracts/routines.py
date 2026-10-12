from pydantic import Field, model_validator

from .domain import Contract


class RoutineCreate(Contract):
    prompt: str = Field(min_length=1, max_length=8000)
    interval_seconds: int | None = Field(default=None, ge=60, le=31536000)
    cron: str | None = None
    timezone: str = "UTC"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule(self) -> "RoutineCreate":
        if (self.interval_seconds is None) == (self.cron is None):
            raise ValueError("one_schedule_required")
        return self
