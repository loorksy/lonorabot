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
    "resume_trading",
    "lift_restriction",
    "resolve_operation",
    "set_account_limits",
    "trust_source",
    "connect_credential",
]
# trust_source: what the owner adds to the trusted list (an MCP server with the tools it
# advertises now, a GitHub owner or repository, or a news feed's domain).
TrustSourceKind = Literal["mcp_server", "github_owner", "github_repo", "feed_domain"]
# connect_credential: which secure form the card offers; "x" names an X MCP server.
CredentialTarget = Literal["mcp_server", "news_feed", "brave_search", "economic_calendar", "broker"]
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
    # trust_source: mcp_server takes connection_id (its tools are read from the server);
    # the others take identifier ("owner", "owner/repository" or a feed domain).
    source_kind: TrustSourceKind | None = None
    connection_id: str | None = Field(default=None, min_length=1, max_length=80)
    identifier: str | None = Field(default=None, min_length=1, max_length=300)
    # connect_credential: the form to offer; service "x" for an X MCP server (D3).
    target: CredentialTarget | None = None
    service: Literal["x"] | None = None

    @model_validator(mode="after")
    def fields_for_kind(self) -> "OwnerActionProposal":
        if self.kind in {"trust_source", "connect_credential"}:
            return self.capability_fields()
        if any(
            value is not None
            for value in (
                self.source_kind,
                self.connection_id,
                self.identifier,
                self.target,
                self.service,
            )
        ):
            raise ValueError("owner_action_fields_invalid")
        return self.trading_fields()

    def capability_fields(self) -> "OwnerActionProposal":
        if (
            self.restriction_id
            or self.operation_id
            or self.account_id
            or self.set_limits
            or self.remove_limits
            or self.currency
            or self.trading_day_timezone
        ):
            raise ValueError("owner_action_fields_invalid")
        if self.kind == "connect_credential":
            if (
                self.target is None
                or self.source_kind
                or self.connection_id
                or self.identifier
                or (self.service is not None and self.target != "mcp_server")
            ):
                raise ValueError("owner_action_fields_invalid")
            return self
        if self.target is not None or self.service is not None or self.source_kind is None:
            raise ValueError("owner_action_fields_invalid")
        if (self.source_kind == "mcp_server") != (self.connection_id is not None) or (
            self.source_kind == "mcp_server"
        ) == (self.identifier is not None):
            raise ValueError("owner_action_fields_invalid")
        if self.identifier is not None:
            from .trusted_sources import normalize_identifier

            self.identifier = normalize_identifier(self.source_kind, self.identifier)
        return self

    def trading_fields(self) -> "OwnerActionProposal":
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


class ConnectedResource(Contract):
    """What the owner's secure form created; never the value it holds."""

    resource: Literal["integration", "mcp", "broker"]
    id: str = Field(min_length=1, max_length=80)


class OwnerActionDecision(Contract):
    """The owner's tap. ``outcome`` answers a resolve card; ``proof`` is the passkey
    assertion a widening card requires (obtained from the card's challenge); ``tier`` is
    what the owner trusts an MCP server for; ``connected`` names what a credential card's
    form created."""

    decision: Literal["confirm", "cancel"]
    tier: Literal["read", "write_nonfinancial"] | None = None
    connected: ConnectedResource | None = None
    outcome: AttestedOutcome | None = None
    note: str | None = Field(default=None, max_length=2000)
    broker_reference: str | None = Field(default=None, max_length=200)
    proof: DeviceProof | None = None
