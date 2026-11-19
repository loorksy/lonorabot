"""Owner action cards: one-tap owner-only actions offered inside the conversation.

A card names one exact effect (its payload) that only the owner's session can confirm,
through the existing owner function for that effect. Agents and the runtime can only
propose a card; no tool can confirm one. A grant card is confirmed with the passkey
ceremony of the grant it builds from its stored draft.
"""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from .account_authority import ALL_AUTHORITY_ACTIONS, AuthorityAction
from .agent_secrets import WORKSPACE_SECRET_NAME
from .devices import DeviceProof
from .domain import Contract

# Cards an agent proposes with owner_action_propose.
OwnerActionKind = Literal[
    "resolve_operation",
    "grant_authority",
    "connect_credential",
    # The Secret card (mandate 10.3, 7.2): fields the agent chooses; the owner's values go
    # straight to the encrypted store as workspace secrets; the agent learns "saved".
    "secret",
]
# Notices of a change an agent made without asking (Q31): "watch_changed" offers Undo of
# an extended watch (one use, while the watch is as the agent left it); "stop_tightened"
# only reports a tightened stop loss (undoing it would be a new financial modification).
NoticeCardKind = Literal["watch_changed", "stop_tightened"]
GrantDuration = Literal["until_stopped", "12h", "24h", "7d"]
# A grant card's one choice: Custom (the markets, actions, duration and own positions the
# card shows; owner decision D1 defaults) or Full delegation (every pair on the account,
# every action and the owner's own positions, until stopped).
GrantDelegation = Literal["custom", "full"]
# connect_credential: which secure form the card offers; "x" names an X MCP server.
CredentialTarget = Literal["mcp_server", "news_feed", "brave_search", "economic_calendar", "broker"]
OwnerActionStatus = Literal["pending", "confirmed", "cancelled", "expired", "superseded"]
AttestedOutcome = Literal["executed", "not_executed", "unknown"]
# The owner's statement when the card's optional note is left empty.
CARD_ATTESTATION = "Owner attested via chat card; not broker confirmation."


class SecretField(Contract):
    """One field of a Secret card: its key names the saved value (an environment variable
    name), its label is shown to the owner; ``secret`` masks it while it is typed.
    Every value is stored encrypted, whatever ``secret`` says."""

    key: str = Field(pattern=WORKSPACE_SECRET_NAME)
    label: str = Field(min_length=1, max_length=60)
    secret: bool = True


class SecretCardSave(Contract):
    """The owner's values for a Secret card's fields, by key; they go to the encrypted
    store and are never kept on the card, in an event or in the conversation."""

    values: dict[
        Annotated[str, Field(pattern=WORKSPACE_SECRET_NAME)],
        Annotated[str, Field(min_length=1, max_length=16000)],
    ] = Field(min_length=1, max_length=8)


class OwnerActionProposal(Contract):
    """Agent tool input. The server validates it against current state and stores the
    exact effect; the card's text comes from the records it names, never from here."""

    kind: OwnerActionKind
    # resolve_operation: the uncertain (ambiguous) operation the owner settles.
    operation_id: str | None = Field(default=None, min_length=1, max_length=80)
    # grant_authority: the account the card grants on.
    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    # grant_authority: a draft the server resolves and the owner signs with the passkey.
    # Omitted fields take the defaults: the agent's own grant, the only connected account
    # (or the agent's focus account), its focus pair (all pairs for Lonora), every action,
    # until the owner stops it, and the owner's own positions excluded.
    agent_id: str | None = Field(default=None, min_length=1, max_length=36)
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=100)
    all_pairs: bool = False
    actions: list[AuthorityAction] | None = Field(default=None, min_length=1, max_length=10)
    duration: GrantDuration | None = None
    allow_manual_positions: bool | None = None
    # "full" preselects Full delegation when the owner's own message asked for it; the
    # other fields still shape the Custom choice the owner can switch back to.
    delegation: GrantDelegation | None = None
    # connect_credential: the form to offer; service "x" for an X MCP server (D3).
    target: CredentialTarget | None = None
    service: Literal["x"] | None = None
    # secret: the card's label and its fields, in the owner's language. Each value is
    # saved under its field's key, the name agents use for it.
    label: str | None = Field(default=None, min_length=1, max_length=80)
    secret_fields: list[SecretField] | None = Field(default=None, min_length=1, max_length=8)

    @model_validator(mode="after")
    def fields_for_kind(self) -> "OwnerActionProposal":
        if self.kind == "secret":
            return self.secret_card_fields()
        if self.label is not None or self.secret_fields is not None:
            raise ValueError("owner_action_fields_invalid")
        if self.kind == "connect_credential":
            return self.capability_fields()
        if self.target is not None or self.service is not None:
            raise ValueError("owner_action_fields_invalid")
        return self.trading_fields()

    def secret_card_fields(self) -> "OwnerActionProposal":
        if (
            self.model_dump(exclude={"kind", "label", "secret_fields"}, exclude_defaults=True)
            or self.label is None
            or self.secret_fields is None
        ):
            raise ValueError("owner_action_fields_invalid")
        keys = [field.key for field in self.secret_fields]
        if len(set(keys)) != len(keys):
            raise ValueError("owner_action_secret_fields_duplicate")
        return self

    def capability_fields(self) -> "OwnerActionProposal":
        if self.operation_id or self.account_id or self.grant_fields():
            raise ValueError("owner_action_fields_invalid")
        if self.target is None or (self.service is not None and self.target != "mcp_server"):
            raise ValueError("owner_action_fields_invalid")
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
                self.delegation,
            )
        )

    def trading_fields(self) -> "OwnerActionProposal":
        grant = self.grant_fields()
        needed = {
            "resolve_operation": ("operation_id",),
            "grant_authority": (),
        }[self.kind]
        for name in ("operation_id", "account_id"):
            if self.kind == "grant_authority" and name == "account_id":
                continue  # Optional: the server resolves the obvious account.
            if (getattr(self, name) is not None) != (name in needed):
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
        return self


class GrantTerms(Contract):
    """What a grant card signs on its account: the markets, actions, duration and the
    owner's own positions."""

    symbol_scope: Literal["selected", "account"]
    symbols: list[str] = Field(default_factory=list[str], max_length=100)
    actions: list[AuthorityAction] = Field(min_length=1, max_length=10)
    duration: GrantDuration = "until_stopped"
    allow_manual_positions: bool = False

    @model_validator(mode="after")
    def scope(self) -> "GrantTerms":
        if (self.symbol_scope == "selected") != bool(self.symbols):
            raise ValueError("authority_exact_symbols_required")
        return self

    def terms(self) -> "GrantTerms":
        return GrantTerms.model_validate(self.model_dump(include=set(GrantTerms.model_fields)))


# Full delegation: every pair on the account, every action, until the owner stops it,
# and the owner's own positions too.
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
    assertion a widening card requires (obtained from the card's challenge); ``connected``
    names what a credential card's form created.

    ``choose`` changes a pending grant card's own choice (``delegation``: Custom or Full
    delegation) in its stored draft and settles nothing; signing still needs the
    confirmation with the passkey.

    A grant card's own choice narrows or widens nothing that needs another signature:
    stopping other agents' grants on that market.
    """

    decision: Literal["confirm", "cancel", "choose"]
    delegation: GrantDelegation | None = None
    connected: ConnectedResource | None = None
    outcome: AttestedOutcome | None = None
    note: str | None = Field(default=None, max_length=2000)
    broker_reference: str | None = Field(default=None, max_length=200)
    proof: DeviceProof | None = None
    stop_authorities: list[str] = Field(default_factory=list[str], max_length=20)


class AccountAuthorityDraft(Contract):
    """The owner's mandate sheet («تنفيذ مفوَّض»): a grant card drafted from the UI. The
    server resolves it like an agent's proposal (the account, the agent's pair, D1
    defaults) and stores it on a pending grant card; nothing is active until the owner
    signs that card with the passkey (its challenge and decision).

    ``mode`` "full" (Q17): every pair on the account for Lonora and flexible agents; a
    fixed-pair agent's full delegation is its own pair only, every action, until
    stopped, the owner's own positions included. Full takes no markets, actions,
    duration or own-positions switch: its terms are fixed. The conflict choice
    (``stop_authorities``) is the card decision's own field."""

    mode: GrantDelegation = "custom"
    thread_id: str | None = Field(default=None, min_length=1, max_length=36)
    account_id: str | None = Field(default=None, min_length=1, max_length=36)
    symbols: list[str] | None = Field(default=None, min_length=1, max_length=100)
    all_pairs: bool = False
    actions: list[AuthorityAction] | None = Field(default=None, min_length=1, max_length=10)
    duration: GrantDuration | None = None
    allow_manual_positions: bool | None = None

    @model_validator(mode="after")
    def terms_for_mode(self) -> "AccountAuthorityDraft":
        if self.mode == "full" and (
            self.symbols is not None
            or self.all_pairs
            or self.actions is not None
            or self.duration is not None
            or self.allow_manual_positions is not None
        ):
            raise ValueError("owner_action_full_delegation_terms_fixed")
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
        )
