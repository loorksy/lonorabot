"""Persistent agents created from the conversation (agent_create) and the owner's form.

Lonora creates agents on its own judgment (mandate 3.1.2): flat, with no template, no
hierarchy and no cap. An instrument or account it assigns is an instruction in the new
agent's method, never a binding. The mode follows 4.3.2 and 4.3.3; only the owner's tap
on the Mandate card ever sets Full by request.
"""

import re
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract
from .trading import TradingMode

# How a persistent agent came to exist: the owner's form, or Lonora (from the owner's
# message the creating run answered, or on its own judgment).
AgentCreatedVia = Literal["owner_ui", "owner_message", "lead"]


# Unicode bidirectional embeddings, overrides, isolates and marks (category Cf).
BIDI_CONTROLS = re.compile("[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def strip_bidi_controls(text: str) -> str:
    return BIDI_CONTROLS.sub("", text)


class AgentCreateInput(Contract):
    """The agent_create tool input and the owner's form. The server resolves the market
    and the account and writes them into the new agent's method."""

    name: str = Field(min_length=1, max_length=80)
    responsibility: str = Field(
        default="",
        max_length=8000,
        description="Its responsibilities and instructions; the owner's words when the owner "
        "asked for it.",
    )
    market: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        description="An instrument to assign, as the broker names it (for gold, XAUUSD); "
        "written into its method.",
    )
    account_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=36,
        description="The account to assign, when several are connected.",
    )
    mode: TradingMode | None = Field(
        default=None,
        description="The mode the owner named for it; ask to create it in Ask on your own. "
        "Omit when no mode was named.",
    )

    @model_validator(mode="after")
    def clean_labels(self) -> "AgentCreateInput":
        # Agent-written labels never carry direction controls: an embedded isolate end or
        # override would reorder the owner's card and pill text around them.
        self.name = " ".join(strip_bidi_controls(self.name).split())
        self.responsibility = strip_bidi_controls(self.responsibility)
        if not self.name:
            raise ValueError("agent_name_required")
        return self
