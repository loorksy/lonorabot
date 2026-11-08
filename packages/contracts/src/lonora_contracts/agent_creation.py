"""Persistent agents created from the conversation (agent_create and its owner cards).

A template names what a new agent is for. It never carries money authority: the
trading template starts at "Ask me" (every trade waits for the owner's tap) and every
other template at "No trading". A grant is only ever signed by the owner.
"""

import re
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract
from .model_routing import ModelSelection

AgentTemplate = Literal["trading", "general", "research", "supervisor"]
# The ladder a new agent starts on: "supervised" is "Ask me", "analysis" is "No trading".
TEMPLATE_LEVEL: dict[str, Literal["analysis", "supervised"]] = {
    "trading": "supervised",
    "general": "analysis",
    "research": "analysis",
    "supervisor": "analysis",
}
# How a persistent agent came to exist: the owner's form, an owner message the
# creating run answered, or the owner's tap on a creation card.
AgentCreatedVia = Literal["owner_ui", "owner_message", "owner_card"]


# Unicode bidirectional embeddings, overrides, isolates and marks (category Cf).
BIDI_CONTROLS = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def strip_bidi_controls(text: str) -> str:
    return BIDI_CONTROLS.sub("", text)



class AgentCreateInput(Contract):
    """The agent_create tool input. The server resolves the market, the account and the
    ladder; nothing here grants authority."""

    template: AgentTemplate
    name: str = Field(min_length=1, max_length=80)
    responsibility: str = Field(
        default="",
        max_length=8000,
        description="What the owner asked this agent to do, in the owner's words where possible.",
    )
    market: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="Trading template only: the focus instrument as the broker names it "
        "(for gold, XAUUSD); the server looks it up in the broker catalog.",
    )
    account_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="Only when the owner chose among several accounts.",
    )
    model: ModelSelection | None = Field(
        default=None, description="Optional: one of the owner's configured models."
    )
    report_to: list[str] = Field(
        default_factory=list[str],
        max_length=5,
        description="Existing agent ids this agent reports important findings to.",
    )
    supervises: list[str] = Field(
        default_factory=list[str],
        max_length=10,
        description="Existing agent ids it supervises (reads, messages, pauses; never trades).",
    )

    @model_validator(mode="after")
    def market_for_template(self) -> "AgentCreateInput":
        # Agent-written labels never carry direction controls: an embedded isolate end or
        # override would reorder the owner's card and pill text around them.
        self.name = " ".join(strip_bidi_controls(self.name).split())
        self.responsibility = strip_bidi_controls(self.responsibility)
        if not self.name:
            raise ValueError("agent_name_required")
        if (self.template == "trading") != (self.market is not None):
            raise ValueError("agent_market_template_mismatch")
        if self.account_id is not None and self.market is None:
            raise ValueError("agent_market_template_mismatch")
        if len(set(self.report_to)) != len(self.report_to):
            raise ValueError("agent_report_to_duplicate")
        if len(set(self.supervises)) != len(self.supervises):
            raise ValueError("supervision_duplicate")
        return self
