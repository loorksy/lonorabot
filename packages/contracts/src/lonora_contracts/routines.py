from datetime import UTC, datetime, timedelta

from pydantic import Field, ValidationInfo, model_validator

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
        description=(
            "One-shot schedule: fire once at this time, then switch the routine off. A one-shot"
            " linked to a goal step fires at this time if its step is current; if the step is"
            " not current yet (an earlier step is pending, or its trade is executing) or the goal"
            " is paused or blocked, it retries every 5 minutes and fires when the step becomes"
            " current. It switches off once it can no longer run: its step is completed, passed"
            " or removed, or the goal has ended."
        ),
    )
    timezone: str = "UTC"
    enabled: bool = True

    @model_validator(mode="after")
    def validate_schedule(self, info: ValidationInfo) -> "RoutineCreate":
        if bool(self.goal_id) != bool(self.step_id):
            raise ValueError("goal_and_step_required_together")
        schedules = [self.interval_seconds, self.cron, self.run_at]
        if sum(value is not None for value in schedules) != 1:
            raise ValueError("one_schedule_required")
        if self.run_at is not None:
            if self.run_at.tzinfo is None:
                raise ValueError("run_at_timezone_required")
            self.run_at = self.run_at.astimezone(UTC)
            # A minute of grace for the form's clock; an enabled earlier time would fire at
            # once. Switching a fired one-shot off stays possible.
            # An edit that neither sets run_at nor switches the routine on passes
            # context {"keep_run_at": True}: its time stays as it is (fired or not).
            context: dict[str, object] = info.context or {}
            keep = bool(context.get("keep_run_at"))
            late = self.run_at < datetime.now(UTC) - timedelta(minutes=1)
            if self.enabled and late and not keep:
                raise ValueError("run_at_past")
        if self.title is not None:
            self.title = self.title.strip() or None
        return self


SCHEDULE_FIELDS = ("interval_seconds", "cron", "run_at")


class RoutineUpdate(Contract):
    """A partial owner edit: fields left out keep their stored value. Sending one schedule
    (interval_seconds, cron or run_at) replaces the other two; the merged routine is checked
    as a RoutineCreate."""

    title: str | None = Field(default=None, max_length=160)
    prompt: str | None = Field(default=None, min_length=1, max_length=8000)
    interval_seconds: int | None = Field(default=None, ge=60, le=31536000)
    cron: str | None = None
    run_at: datetime | None = None
    timezone: str | None = None
    enabled: bool | None = None
