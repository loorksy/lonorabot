"""Lonora's lead tools (agent_inspect, agent_control): read and steer team agents.

No team agent reads or steers another, and no control carries money authority: Lonora
reads, messages, pauses and resumes a team agent's work, cancels its current run, switches
it to Ask or deletes it, and never trades for it or lifts a brake (3.1.2, 3.3.1).
"""

from typing import Literal, Self

from pydantic import Field, model_validator

from .domain import Contract

InspectSection = Literal["overview", "work", "runs", "decisions", "operations", "memory"]
# Every action is Lonora's alone (mandate 3.1.2, 3.3.1).
ControlAction = Literal["pause", "resume", "message", "cancel_run", "set_ask", "delete"]
ControlTarget = Literal["agent", "task", "routine", "watch"]


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
        if self.action in {"message", "cancel_run", "set_ask", "delete"} and (
            self.target != "agent" or self.target_id
        ):
            raise ValueError("agent_control_fields_invalid")
        if (self.target == "agent") != (self.target_id is None):
            raise ValueError("agent_control_fields_invalid")
        return self
