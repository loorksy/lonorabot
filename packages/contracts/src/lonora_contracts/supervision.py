"""Supervision: one agent reads and steers another's work through a visible grant.

A grant never carries money authority: the supervisor reads, messages, pauses and
resumes the supervised agent's work, and never trades for it, uses its grant or lifts
a brake. Lonora leads every team agent by its role, with no grant (lonora_db.lead);
the owner revokes any grant with one tap.
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .domain import Contract

InspectSection = Literal["overview", "work", "runs", "decisions", "operations", "memory"]
ControlAction = Literal["pause", "resume", "message"]
ControlTarget = Literal["agent", "task", "routine", "watch"]


class SupervisionCreate(Contract):
    """The owner's own grant from the profile (one tap; supervision is never money)."""

    supervisor_id: str = Field(min_length=1, max_length=36)
    supervised_id: str = Field(min_length=1, max_length=36)


class AgentInspectInput(Contract):
    # An id, or the agent's name (agent names run to 80 characters).
    agent_id: str = Field(min_length=1, max_length=80)
    section: InspectSection = "overview"
    page: int = Field(default=0, ge=0, le=50)


class AgentControlInput(Contract):
    agent_id: str = Field(min_length=1, max_length=80)
    action: ControlAction
    target: ControlTarget = "agent"
    target_id: str | None = Field(default=None, min_length=1, max_length=36)
    message: str | None = Field(default=None, min_length=1, max_length=8000)

    @model_validator(mode="after")
    def fields_for_action(self) -> Self:
        if (self.action == "message") != (self.message is not None):
            raise ValueError("agent_control_fields_invalid")
        if self.action == "message" and (self.target != "agent" or self.target_id):
            raise ValueError("agent_control_fields_invalid")
        if (self.target == "agent") != (self.target_id is None):
            raise ValueError("agent_control_fields_invalid")
        return self


class SupervisionChange(Contract):
    """The supervision tool input: who supervises whom, from the owner's message."""

    action: Literal["grant", "revoke"]
    supervisor_id: str | None = Field(
        default=None, min_length=1, max_length=36, description="Default: yourself."
    )
    supervised_ids: list[str] = Field(min_length=1, max_length=10)

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.supervised_ids)) != len(self.supervised_ids):
            raise ValueError("supervision_duplicate")
        return self
