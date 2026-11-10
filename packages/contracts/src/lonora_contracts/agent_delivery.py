"""Per-agent delivery rules (owner decision Q47): how one agent's own alerts reach the owner.

The rules only narrow delivery inside Lonora, the one channel to the owner (Q53). A
critical or action_required item always shows (Q4); a rule never grants anything.
``daily_limit`` counts the agent's non-urgent alerts since the owner's local midnight;
beyond it (or with ``in_app`` off) an alert stays in Activity only. ``calls`` off means
the agent never rings the owner, whatever the owner-wide reach-me channel says.
"""

from pydantic import Field

from .domain import Contract


class AgentDeliveryRules(Contract):
    in_app: bool = True
    calls: bool = True
    daily_limit: int | None = Field(default=None, ge=1, le=100)


class AgentDeliveryRulesUpdate(Contract):
    in_app: bool | None = None
    calls: bool | None = None
    daily_limit: int | None = Field(default=None, ge=1, le=100)
