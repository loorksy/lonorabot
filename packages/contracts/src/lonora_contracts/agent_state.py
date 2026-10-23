"""One truthful, bounded projection consumed by chat, voice and both clients."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from .domain import Contract


class AgentLiveState(Contract):
    agent_id: str
    observed_at: datetime
    state: Literal["idle", "working", "waiting", "action_required", "degraded", "paused"]
    phase: str
    reason_code: str | None = None
    reason_params: dict[str, str | int] = Field(default_factory=dict[str, str | int])
    tasks: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=3)
    runs: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
    runtime_waits: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
    pending_approval_count: int = 0
    watch_count: int = 0
    pending_authorization_count: int = 0
    super_bot: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=3)
    account_authorities: list[dict[str, Any]] = Field(
        default_factory=list[dict[str, Any]], max_length=3
    )
    collaborations: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=3)
    health: list[dict[str, Any]] = Field(default_factory=list[dict[str, Any]], max_length=6)
