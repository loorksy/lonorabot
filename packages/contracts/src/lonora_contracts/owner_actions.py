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

from .account_authority import ALL_AUTHORITY_ACTIONS, AuthorityAction
from .devices import DeviceProof
from .domain import Contract
from .trading import TradingMode

# Cards an agent proposes with owner_action_propose.
OwnerActionKind = Literal[
    "resume_trading",
    "lift_restriction",
    "resolve_operation",
    "set_account_limits",
    "grant_authority",
    "trust_source",
    "connect_credential",
    # The Mandate card (mandate 10.3): the agent's mode read live and one button for the
    # other mode. It stays the agent's switch after a tap.
    "trading_mode",
]
# Model cards (W15-10), raised only by model_request: "agent_model" asks the owner to
# use a model for an agent; "agent_model_changed" offers Undo of a switch that applied.
ModelCardKind = Literal["agent_model", "agent_model_changed"]
MODEL_CARD_KINDS: tuple[ModelCardKind, ...] = ("agent_model", "agent_model_changed")
# Notices of a change an agent made without asking (Q31): "watch_changed" offers Undo of
# an extended watch (one use, while the watch is as the agent left it); "stop_tightened"
# only reports a tightened stop loss (undoing it would be a new financial modification).
NoticeCardKind = Literal["watch_changed", "stop_tightened"]
GrantDuration = Literal["until_stopped", "12h", "24h", "7d"]
# A grant card's one choice: Custom (the markets, actions, duration, daily loss limit and
# own positions the card shows; owner decision D1 defaults) or Full delegation (every
# pair on the account, every action and the owner's own positions, until stopped, with
# no daily loss limit from the card). The account's own money limits bind both.
GrantDelegation = Literal["custom", "full"]
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
    # grant_authority: a draft the server resolves and the owner signs with the passkey.
    # Omitted fields take the defaults: the agent's own grant, the only connected account
    # (or the agent's focus account), its focus pair (all pairs for Lonora), every action,
    # until the owner stops it, the owner's own positions excluded, and a daily loss
    # limit suggested at 3% of current equity unless the owner named one.
    agent_id: str | None = Field(default=None, min_length=1, max_length=36)
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=100)
    all_pairs: bool = False
    actions: list[AuthorityAction] | None = Field(default=None, min_length=1, max_length=10)
    duration: GrantDuration | None = None
    allow_manual_positions: bool | None = None
    daily_loss_percent: Decimal | None = Field(default=None, gt=0, le=100)
    daily_loss_amount: Decimal | None = Field(default=None, gt=0)
    # "full" preselects Full delegation when the owner's own message asked for it; the
    # other fields still shape the Custom choice the owner can switch back to.
    delegation: GrantDelegation | None = None
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
        if self.kind == "trading_mode":
            # Only the agent whose mode it switches (the proposer's own when omitted).
            if self.model_dump(exclude={"kind", "agent_id"}, exclude_defaults=True):
                raise ValueError("owner_action_fields_invalid")
            return self
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
            or self.grant_fields()
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

    def grant_fields(self) -> bool:
        """Whether any grant_authority draft field is set."""
        return any(
            value not in (None, False)
            for value in (
                self.agent_id,
                self.symbols,
                self.all_pairs,
                self.actions,
                self.duration,
                self.allow_manual_positions,
                self.daily_loss_percent,
                self.daily_loss_amount,
                self.delegation,
            )
        )

    def trading_fields(self) -> "OwnerActionProposal":
        limits = bool(
            self.set_limits or self.remove_limits or self.currency or self.trading_day_timezone
        )
        grant = self.grant_fields()
        needed = {
            "resume_trading": (),
            "lift_restriction": ("restriction_id",),
            "resolve_operation": ("operation_id",),
            "set_account_limits": ("account_id",),
            "grant_authority": (),
        }[self.kind]
        for name in ("restriction_id", "operation_id", "account_id"):
            if self.kind == "grant_authority" and name == "account_id":
                continue  # Optional: the server resolves the obvious account.
            if (getattr(self, name) is not None) != (name in needed):
                raise ValueError("owner_action_fields_invalid")
        if limits != (self.kind == "set_account_limits"):
            raise ValueError("owner_action_fields_invalid")
        if grant and self.kind != "grant_authority":
            raise ValueError("owner_action_fields_invalid")
        if self.symbols is not None and (
            self.all_pairs
            or len(set(self.symbols)) != len(self.symbols)
            or any(not item or len(item) > 80 or item.strip() != item for item in self.symbols)
        ):
            raise ValueError("authority_exact_symbols_required")
        if self.actions is not None and len(set(self.actions)) != len(self.actions):
            raise ValueError("authority_duplicate_scope")
        if self.daily_loss_percent is not None and self.daily_loss_amount is not None:
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


class DailyLossDraft(Contract):
    """The daily loss limit a grant card sets on the account: an amount in the account
    currency, from the owner's own words (requested) or 3% of equity (suggested)."""

    amount: Decimal = Field(gt=0)
    currency: str = Field(min_length=1, max_length=16)
    basis: Literal["suggested", "requested"]
    percent: Decimal | None = Field(default=None, gt=0, le=100)
    equity: Decimal | None = Field(default=None, gt=0)


class GrantTerms(Contract):
    """What a grant card signs on its account: the markets, actions, duration, the
    owner's own positions and the daily loss limit the card sets."""

    symbol_scope: Literal["selected", "account"]
    symbols: list[str] = Field(default_factory=list[str], max_length=100)
    actions: list[AuthorityAction] = Field(min_length=1, max_length=10)
    duration: GrantDuration = "until_stopped"
    allow_manual_positions: bool = False
    daily_loss: DailyLossDraft | None = None

    @model_validator(mode="after")
    def scope(self) -> "GrantTerms":
        if (self.symbol_scope == "selected") != bool(self.symbols):
            raise ValueError("authority_exact_symbols_required")
        return self

    def terms(self) -> "GrantTerms":
        return GrantTerms.model_validate(self.model_dump(include=set(GrantTerms.model_fields)))


# Full delegation: every pair on the account, every action, until the owner stops it,
# the owner's own positions too, and no daily loss limit set by the card.
FULL_TERMS = GrantTerms(
    symbol_scope="account",
    actions=list(ALL_AUTHORITY_ACTIONS),
    duration="until_stopped",
    allow_manual_positions=True,
)


class GrantDraft(GrantTerms):
    """A grant card's stored, server-resolved draft. The signed envelope is built only
    from this and the owner's own choices on the card, never from model text.

    ``delegation`` is the owner's choice on the card. Under Full the draft's own terms
    are exactly ``FULL_TERMS`` (what is signed) and ``custom`` keeps the Custom terms,
    so switching back restores them as they were."""

    agent_id: str = Field(min_length=1, max_length=36)
    account_id: str = Field(min_length=1, max_length=120)
    delegation: GrantDelegation = "custom"
    custom: GrantTerms | None = None

    @model_validator(mode="after")
    def delegation_terms(self) -> "GrantDraft":
        if self.delegation == "full":
            if self.custom is None or not same_terms(self.terms(), FULL_TERMS):
                raise ValueError("owner_action_delegation_invalid")
        elif self.custom is not None:
            raise ValueError("owner_action_delegation_invalid")
        return self

    def with_delegation(self, choice: GrantDelegation) -> "GrantDraft":
        """The same card with the owner's other choice: Full signs ``FULL_TERMS``;
        Custom restores the terms the card had before Full was chosen."""
        if choice == self.delegation:
            return self
        owner = {"agent_id": self.agent_id, "account_id": self.account_id}
        if choice == "full":
            return GrantDraft(
                **owner, **FULL_TERMS.model_dump(), delegation="full", custom=self.terms()
            )
        assert self.custom is not None
        return GrantDraft(**owner, **self.custom.model_dump(), delegation="custom")


def same_terms(left: GrantTerms, right: GrantTerms) -> bool:
    """Equal terms, with actions compared as a set."""
    return left.model_dump(exclude={"actions"}) == right.model_dump(exclude={"actions"}) and set(
        left.actions
    ) == set(right.actions)


class OwnerActionChallenge(Contract):
    """The owner's choice on a grant card that changes what is signed: including the
    positions the owner opened manually (Custom only; Full delegation always includes
    them). Sent with the passkey challenge.

    ``delegation`` is the choice the owner's card showed when he tapped (Web and Mobile
    always send it). The challenge is refused when it differs from the card's stored
    draft, so the passkey never signs a choice his screen did not show; the card is
    read again instead."""

    delegation: GrantDelegation | None = None
    allow_manual_positions: bool | None = None


class ConnectedResource(Contract):
    """What the owner's secure form created; never the value it holds."""

    resource: Literal["integration", "mcp", "broker"]
    id: str = Field(min_length=1, max_length=80)


class OwnerActionDecision(Contract):
    """The owner's tap. ``outcome`` answers a resolve card; ``proof`` is the passkey
    assertion a widening card requires (obtained from the card's challenge); ``tier`` is
    what the owner trusts an MCP server for; ``connected`` names what a credential card's
    form created.

    ``choose`` changes a pending grant card's own choice (``delegation``: Custom or Full
    delegation) in its stored draft and settles nothing; signing still needs the
    confirmation with the passkey.

    A grant card's own choices narrow or widen nothing that needs another signature:
    leaving the account without the suggested daily loss limit (``money_limit``
    "none"), resuming new trading, and stopping other agents' grants on that market.
    """

    decision: Literal["confirm", "cancel", "choose"]
    # The Mandate card: the mode its button showed at the moment of the tap.
    trading_mode: TradingMode | None = None
    delegation: GrantDelegation | None = None
    tier: Literal["read", "write_nonfinancial"] | None = None
    connected: ConnectedResource | None = None
    outcome: AttestedOutcome | None = None
    note: str | None = Field(default=None, max_length=2000)
    broker_reference: str | None = Field(default=None, max_length=200)
    proof: DeviceProof | None = None
    money_limit: Literal["apply", "none"] = "apply"
    resume_trading: bool = False
    stop_authorities: list[str] = Field(default_factory=list[str], max_length=20)
    # A resolve card answered «غير معروف»: also pause new trades on its account until the
    # end of the trading day (an owner restriction; it only narrows). Only with "unknown".
    pause_new_today: bool = False

    @model_validator(mode="after")
    def pause_only_when_unknown(self) -> "OwnerActionDecision":
        if self.pause_new_today and (self.decision != "confirm" or self.outcome != "unknown"):
            raise ValueError("owner_action_pause_unknown_only")
        return self


class AccountAuthorityDraft(Contract):
    """The owner's mandate sheet («تنفيذ مفوَّض»): a grant card drafted from the UI. The
    server resolves it like an agent's proposal (the account, the agent's pair, D1
    defaults) and stores it on a pending grant card; nothing is active until the owner
    signs that card with the passkey (its challenge and decision).

    ``mode`` "full" (Q17): every pair on the account for Lonora and flexible agents; a
    fixed-pair agent's full delegation is its own pair only, every action, until
    stopped, the owner's own positions included. Full takes no markets, actions,
    duration, daily loss or own-positions switch: its terms are fixed. The money-limit
    choice («التشغيل دون حد مالي»: ``money_limit`` "none") and the conflict choice
    (``stop_authorities``) are the card decision's own fields."""

    mode: GrantDelegation = "custom"
    thread_id: str | None = Field(default=None, min_length=1, max_length=36)
    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=100)
    all_pairs: bool = False
    actions: list[AuthorityAction] | None = Field(default=None, min_length=1, max_length=10)
    duration: GrantDuration | None = None
    allow_manual_positions: bool | None = None
    # Q16: an amount in the account currency, or a percentage of equity now.
    daily_loss_amount: Decimal | None = Field(default=None, gt=0)
    daily_loss_percent: Decimal | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def terms_for_mode(self) -> "AccountAuthorityDraft":
        if self.mode == "full" and (
            self.symbols is not None
            or self.all_pairs
            or self.actions is not None
            or self.duration is not None
            or self.allow_manual_positions is not None
            or self.daily_loss_amount is not None
            or self.daily_loss_percent is not None
        ):
            raise ValueError("owner_action_full_delegation_terms_fixed")
        if self.daily_loss_amount is not None and self.daily_loss_percent is not None:
            raise ValueError("owner_action_fields_invalid")
        return self

    def proposal(self, agent_id: str) -> OwnerActionProposal:
        """The same resolution an agent's grant proposal goes through."""
        return OwnerActionProposal(
            kind="grant_authority",
            agent_id=agent_id,
            account_id=self.account_id,
            symbols=self.symbols,
            all_pairs=self.all_pairs,
            actions=self.actions,
            duration=self.duration,
            allow_manual_positions=self.allow_manual_positions,
            daily_loss_amount=self.daily_loss_amount,
            daily_loss_percent=self.daily_loss_percent,
        )
