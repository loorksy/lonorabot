from typing import Any, Literal

from pydantic import Field

from .domain import Contract

WORK_TRIGGERS = frozenset(
    {
        "tickets",
        "routine",
        "watch",
        "webhook",
        "subagent",
        "broker_event",
        "activation",
        "workspace_wake",
    }
)

RunStatus = Literal[
    "queued",
    "leased",
    "running",
    "waiting_input",
    "waiting_takeover",
    "completed",
    "failed",
    "cancelled",
]


class RunFailure(Contract):
    """Why a Run failed, by the provider's error family (Q22), on ``run.failed`` and Run.

    ``retry_after_seconds`` is the provider's own ``Retry-After`` hint when it sent one,
    counted from the failure; the client never invents a countdown.
    """

    family: Literal["quota", "rate", "timeout", "model", "other"]
    retry_after_seconds: int | None = Field(default=None, ge=0)


class RunRequest(Contract):
    thread_id: str
    agent_id: str
    trigger: str = "user"
    prompt: str = Field(default="", max_length=30000)
    parent_run_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class Lease(Contract):
    run_id: str
    owner: str
    fence: int


class SteeringInput(Contract):
    content: str = Field(min_length=1, max_length=30000)
