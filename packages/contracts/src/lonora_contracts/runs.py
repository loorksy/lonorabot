from typing import Any, Literal

from pydantic import Field

from .domain import Contract

WORK_TRIGGERS = frozenset(
    {"tickets", "routine", "watch", "webhook", "subagent", "broker_event", "activation"}
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
