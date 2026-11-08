"""Owner action cards: one-tap owner-only actions offered inside the conversation.

A card names one exact effect (its payload) that only the owner's session can confirm,
through the existing owner function for that effect. Agents and the runtime can only
propose a card; no tool can confirm one. Widening money authority (raising or removing
a money limit) also needs a verified passkey assertion bound to the card's payload.
"""

from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from .domain import Contract
from .super_bot import DeviceProof

OwnerActionKind = Literal[
    "resume_trading", "lift_restriction", "resolve_operation", "set_account_limits"
]
OwnerActionStatus = Literal["pending", "confirmed", "cancelled", "expired", "superseded"]
MoneyLimitName = Literal[
    "max_trade_risk",
    "max_trade_risk_equity_percent",
    "max_daily_loss",
    "max_open_risk",
    "max_open_risk_equity_percent",
    "min_free_margin",
]
AttestedOutcome = Literal["executed", "not_executed", "unknown"]
# The owner's statement when the card's optional note is left empty.
CARD_ATTESTATION = "Owner attested via chat card; not broker confirmation."


class OwnerActionProposal(Contract):
    """Agent tool input. The server validates it against current state and stores the
    exact effect; the card's text comes from the records it names, never from here."""

    kind: OwnerActionKind
    # lift_restriction: the active or scheduled restriction to lift.
    restriction_id: str | None = Field(default=None, min_length=1, max_length=36)
    # resolve_operation: the uncertain (ambiguous) operation the owner settles.
    operation_id: str | None = Field(default=None, min_length=1, max_length=80)
    # set_account_limits: the account and the exact limit changes.
    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    set_limits: dict[MoneyLimitName, Decimal] = Field(default_factory=dict[MoneyLimitName, Decimal])
    remove_limits: list[MoneyLimitName] = Field(default_factory=list[MoneyLimitName], max_length=6)
    currency: str | None = Field(default=None, min_length=1, max_length=16)
    trading_day_timezone: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def fields_for_kind(self) -> "OwnerActionProposal":
        limits = bool(
            self.set_limits or self.remove_limits or self.currency or self.trading_day_timezone
        )
        needed = {
            "resume_trading": (),
            "lift_restriction": ("restriction_id",),
            "resolve_operation": ("operation_id",),
            "set_account_limits": ("account_id",),
        }[self.kind]
        for name in ("restriction_id", "operation_id", "account_id"):
            if (getattr(self, name) is not None) != (name in needed):
                raise ValueError("owner_action_fields_invalid")
        if limits != (self.kind == "set_account_limits"):
            raise ValueError("owner_action_fields_invalid")
        if set(self.set_limits) & set(self.remove_limits):
            raise ValueError("owner_action_limit_conflict")
        for name, value in self.set_limits.items():
            if value <= 0 or (name.endswith("_percent") and value > 100):
                raise ValueError("owner_action_limit_invalid")
        if self.currency is not None:
            self.currency = self.currency.strip()
            if not self.currency:
                raise ValueError("risk_currency_required")
        if self.trading_day_timezone is not None:
            try:
                ZoneInfo(self.trading_day_timezone)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise ValueError("trading_day_timezone_invalid") from error
        return self


class OwnerActionDecision(Contract):
    """The owner's tap. ``outcome`` answers a resolve card; ``proof`` is the passkey
    assertion a widening card requires (obtained from the card's challenge)."""

    decision: Literal["confirm", "cancel"]
    outcome: AttestedOutcome | None = None
    note: str | None = Field(default=None, max_length=2000)
    broker_reference: str | None = Field(default=None, max_length=200)
    proof: DeviceProof | None = None
