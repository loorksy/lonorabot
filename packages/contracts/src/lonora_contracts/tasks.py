"""Durable logical work, independent from its leased execution attempts."""

from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract

TaskStatus = Literal["queued", "running", "waiting", "paused", "completed", "failed", "cancelled"]
TaskRecovery = Literal["automatic", "owner", "reconcile", "modify_plan", "terminal"]


class TaskRetryPolicy(Contract):
    mode: Literal["owner", "automatic"] = "owner"
    maximum_attempts: int = Field(default=3, ge=1, le=5)
    initial_delay_seconds: int = Field(default=15, ge=5, le=300)


class TaskFailure(Contract):
    run_id: str
    lease_fence: int
    code: str
    failed_step_id: str | None = None
    attempt: int = Field(ge=1)
    recovery: TaskRecovery
    reconciliation: Literal["financial", "external"] | None = None
    next_retry_at: str | None = None


class TaskStep(Contract):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=300)
    state: Literal["pending", "running", "completed", "skipped", "failed"] = "pending"
    evidence_call_ids: list[str] = Field(default_factory=list[str], max_length=16)
    side_effect: Literal["read_only", "idempotent", "mutating", "irreversible"] = "mutating"


class TaskCreate(Contract):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=16000)
    steps: list[TaskStep] = Field(default_factory=list[TaskStep], max_length=50)
    retry_policy: TaskRetryPolicy = Field(default_factory=TaskRetryPolicy)

    @model_validator(mode="after")
    def unique_steps(self) -> "TaskCreate":
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("task_step_duplicate")
        if any(step.state != "pending" for step in self.steps):
            raise ValueError("task_step_initial_state")
        return self


class TaskState(Contract):
    schema_version: Literal[1] = 1
    origin_thread_id: str
    status: TaskStatus = "queued"
    phase: str = "queued"
    waiting_reason: str | None = None
    steps: list[TaskStep] = Field(default_factory=list[TaskStep], max_length=50)
    plan_revision: int = 1
    control_requested: Literal["pause", "cancel"] | None = None
    instruction: str = Field(default="", max_length=8000)
    last_checkpoint_at: str | None = None
    attempt: int = Field(default=1, ge=1)
    retry_policy: TaskRetryPolicy = Field(default_factory=TaskRetryPolicy)
    failure: TaskFailure | None = None


class TaskInspect(Contract):
    task_id: str | None = None


class TaskControl(Contract):
    task_id: str
    action: Literal["pause", "resume", "cancel", "revise"]
    expected_version: int = Field(ge=1)
    instruction: str = Field(default="", max_length=8000)
    steps: list[TaskStep] | None = Field(default=None, max_length=50)


class TaskStepUpdate(Contract):
    step_id: str
    plan_revision: int = Field(ge=1)
    state: Literal["running", "completed"]
    evidence_call_ids: list[str] = Field(default_factory=list[str], max_length=16)
