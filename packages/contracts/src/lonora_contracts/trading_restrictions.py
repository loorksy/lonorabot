"""Owner restrictions: durable, scoped, expiring narrowing of what may be admitted.

A restriction never grants anything. It narrows the actions the financial execution
boundary admits for an account, optionally one agent and one exact broker symbol, for a
time window. It is enforced at execution, so queued and in-flight work is covered; an
operation already sent to the broker is not reversed by it.
"""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .domain import Contract

# no_new_entries    no new market or pending entry and no pending-entry edit; position
#                   management, closes and cancellations stay admissible.
# no_risk_increase  only risk-reducing actions (close, cancel an order that would add
#                   exposure, tighten/add a stop-loss). Closing a hedge leg stays an exit;
#                   cancelling a protective opposite-side order removes protection.
# all_mutations     no broker mutation at all in the scope, reduce-only included.
RestrictionActionClass = Literal["no_new_entries", "no_risk_increase", "all_mutations"]
# owner_ui          created by the authenticated owner directly.
# owner_message     created by an agent acting on the owner's message (source_message_id).
# agent             created by an agent on its own initiative (narrowing only).
RestrictionSource = Literal["owner_ui", "owner_message", "agent"]
RestrictionState = Literal["scheduled", "active", "expired", "revoked"]


def _window(valid_from: datetime | None, valid_until: datetime | None) -> None:
    if valid_from is not None and valid_until is not None and valid_until <= valid_from:
        raise ValueError("restriction_window_invalid")


class TradingRestrictionCreate(Contract):
    """Owner-authored restriction (owner session only)."""

    account_id: str = Field(min_length=1, max_length=36)
    agent_id: str | None = Field(default=None, min_length=1, max_length=36)
    symbol: str | None = Field(default=None, min_length=1, max_length=80)
    action_class: RestrictionActionClass
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    reason: str = Field(default="", max_length=1000)
    # Owner-manual operations are exempt unless the owner explicitly includes them. The
    # flag binds the owner's own trades, so it is only valid on an all-agent restriction:
    # a restriction scoped to one agent never restricts the owner.
    applies_to_owner_manual: bool = False

    @model_validator(mode="after")
    def window(self) -> "TradingRestrictionCreate":
        if self.applies_to_owner_manual and self.agent_id is not None:
            raise ValueError("restriction_owner_manual_agent_conflict")
        _window(self.valid_from, self.valid_until)
        self.reason = self.reason.strip()
        return self


class AgentRestrictionRequest(Contract):
    """Agent tool input. A restriction can only narrow; lifting one is the owner's action."""

    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    symbol: str | None = Field(default=None, min_length=1, max_length=80)
    # Every symbol on the account. Without it, an agent with a home market on that account
    # has its home symbol filled in, like every other market tool.
    all_symbols: bool = False
    agent_id: str | None = Field(default=None, min_length=1, max_length=36)
    all_agents: bool = False
    action_class: RestrictionActionClass
    valid_from: AwareDatetime | None = None
    valid_until: AwareDatetime | None = None
    reason: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def scope(self) -> "AgentRestrictionRequest":
        if self.all_agents and self.agent_id is not None:
            raise ValueError("restriction_agent_scope_conflict")
        if self.all_symbols and self.symbol is not None:
            raise ValueError("restriction_symbol_scope_conflict")
        _window(self.valid_from, self.valid_until)
        self.reason = self.reason.strip()
        if not self.reason:
            raise ValueError("restriction_reason_required")
        return self


class RestrictionRevoke(Contract):
    reason: str = Field(default="", max_length=1000)


class RestrictionListQuery(Contract):
    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    include_ended: bool = False
    limit: int = Field(default=20, ge=1, le=50)
