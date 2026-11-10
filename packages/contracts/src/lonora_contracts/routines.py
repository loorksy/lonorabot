from datetime import datetime

from pydantic import Field, model_validator

from .domain import Contract


class RoutineCreate(Contract):
    goal_id: str | None = None
    step_id: str | None = None
    title: str | None = Field(default=None, max_length=160)
    prompt: str = Field(min_length=1, max_length=8000)
    interval_seconds: int | None = Field(default=None, ge=60, le=31536000)
    cron: str | None = None
    run_at: datetime | None = Field(
        default=None,
        description="One-shot schedule: fire once at this time, then switch the routine off.",
    )
    timezone: str = "UTC"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule(self) -> "RoutineCreate":
        if bool(self.goal_id) != bool(self.step_id):
            raise ValueError("goal_and_step_required_together")
        schedules = [self.interval_seconds, self.cron, self.run_at]
        if sum(value is not None for value in schedules) != 1:
            raise ValueError("one_schedule_required")
        if self.run_at is not None and self.run_at.tzinfo is None:
            raise ValueError("run_at_timezone_required")
        if self.title is not None:
            self.title = self.title.strip() or None
        return self
