"""Informational Agent questions. These contracts never confer execution authority."""

from typing import Any

from pydantic import Field

from .domain import Contract


# One call a choice stands for; the agent carries it out as its own call. The model reads
# this schema in every turn, so neither it nor `actions` carries a description or bounds:
# the tool's description says what they are, and what can be bound is checked when the
# question is asked (lonora_agent.offers).
class BoundAction(Contract):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict[str, Any])


class InputChoice(Contract):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=240)
    # The exact calls made if this choice is picked; empty when it changes nothing.
    actions: list[BoundAction] = Field(default_factory=list[BoundAction], max_length=6)
