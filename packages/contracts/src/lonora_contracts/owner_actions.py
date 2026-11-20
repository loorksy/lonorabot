"""Owner action cards: one-tap owner-only actions offered inside the conversation.

A card names one exact effect (its payload) that only the owner's session can confirm,
through the existing owner function for that effect. Agents and the runtime can only
propose a card; no tool can confirm one. There is no grant card: proposing that kind
is a validation error.
"""

from typing import Annotated, Literal, get_args

from pydantic import Field, field_validator, model_validator

from .account_authority import ALL_AUTHORITY_ACTIONS
from .agent_secrets import WORKSPACE_SECRET_NAME
from .domain import Contract
from .model_routing import PROVIDER_KEY_NAMES, ProviderId
from .trading import AuthorityAction, TradingMode

# Cards an agent proposes with owner_action_propose.
OwnerActionKind = Literal[
    "settle_operation",
    # The Mandate card (mandate 10.3): the agent's mode read live and one button for the
    # other mode. It stays the agent's switch after a tap.
    "trading_mode",
    # The Secret card (mandate 10.3, 7.2): the owner's values go straight to the encrypted
    # store; the agent learns which keys were saved.
    "secret",
]
GrantDuration = Literal["until_stopped", "12h", "24h", "7d"]
# A grant card's one choice: Custom (the markets, actions, duration and own positions the
# card shows; owner decision D1 defaults) or Full delegation (every pair on the account,
# every action and the owner's own positions, until stopped).
GrantDelegation = Literal["custom", "full"]
# A Secret card that connects something: the server sets its fields and destination, and
# saving it creates the connection. "x" names an X MCP server. A trading account is
# connected with broker_connect's card instead. "model_provider" takes the provider's id
# as its name.
CredentialTarget = Literal[
    "mcp_server", "news_feed", "brave_search", "economic_calendar", "model_provider"
]
OwnerActionStatus = Literal["pending", "confirmed", "cancelled", "expired", "superseded"]
AttestedOutcome = Literal["executed", "not_executed", "unknown"]
# The statement recorded with a Settle card's answer: the owner's word, never the broker's.
CARD_ATTESTATION = "Owner attested via chat card; not broker confirmation."


class SecretField(Contract):
    """One field of a Secret card: its key names the saved value (an environment variable
    name), its label is shown to the owner; ``secret`` masks it while it is typed.
    Every value is stored encrypted, whatever ``secret`` says."""

    key: str = Field(pattern=WORKSPACE_SECRET_NAME)
    label: str = Field(min_length=1, max_length=60)
    secret: bool = True


class SecretCardSave(Contract):
    """The owner's values for a Secret card's fields, by key (an optional field left empty
    is left out); they go to the encrypted store and are never kept on the card, in an
    event or in the conversation."""

    values: dict[
        Annotated[str, Field(pattern=WORKSPACE_SECRET_NAME)],
        Annotated[str, Field(min_length=1, max_length=16000)],
    ] = Field(max_length=8)


class OwnerActionProposal(Contract):
    """Agent tool input. The server validates it against current state and stores the
    exact effect; the card's text comes from the records it names, never from here, but
    for a Secret card's label, field labels and the details the agent gave from chat."""

    kind: OwnerActionKind
    # settle_operation: the uncertain (ambiguous) operation the owner settles.
    operation_id: str | None = Field(default=None, min_length=1, max_length=80)
    # trading_mode: the agent whose mode the Mandate card switches. Omitted, it is the
    # proposer's own agent.
    agent_id: str | None = Field(default=None, min_length=1, max_length=36)
    # secret: the card's label and its fields, in the owner's language. Each value is
    # saved under its field's key, the name agents use for it.
    label: str | None = Field(default=None, min_length=1, max_length=80)
    secret_fields: list[SecretField] | None = Field(default=None, min_length=1, max_length=8)
    # secret with target: a card that connects it. The non-secret detail comes from the
    # owner's words in chat: a name. The card asks for the secret and for an address (an
    # MCP server's, a feed's), which may carry a key.
    target: CredentialTarget | None = None
    service: Literal["x"] | None = None
    name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def detail_text(cls, value: str | None) -> str | None:
        # A detail from chat, without the spaces around it; blank is no detail.
        if value is not None and not value.strip():
            raise ValueError("owner_action_fields_invalid")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def fields_for_kind(self) -> "OwnerActionProposal":
        if self.kind == "trading_mode":
            # Only the agent whose mode it switches (the proposer's own when omitted).
            if self.model_dump(exclude={"kind", "agent_id"}, exclude_defaults=True):
                raise ValueError("owner_action_fields_invalid")
            return self
        if self.kind == "secret":
            return self.secret_card_fields()
        if self.kind != "settle_operation" or self.operation_id is None:
            raise ValueError("owner_action_fields_invalid")
        if self.model_dump(exclude={"kind", "operation_id"}, exclude_defaults=True):
            raise ValueError("owner_action_fields_invalid")
        return self

    def secret_card_fields(self) -> "OwnerActionProposal":
        own = {"kind", "label", "secret_fields", "target", "service", "name"}
        if self.model_dump(exclude=own, exclude_defaults=True):
            raise ValueError("owner_action_fields_invalid")
        if self.target is None:
            # The agent's own card: its label and fields, nothing else.
            if (
                self.label is None
                or self.secret_fields is None
                or any(v is not None for v in (self.service, self.name))
            ):
                raise ValueError("owner_action_fields_invalid")
            keys = [field.key for field in self.secret_fields]
            if len(set(keys)) != len(keys):
                raise ValueError("owner_action_secret_fields_duplicate")
            if set(keys) & set(PROVIDER_KEY_NAMES.values()):
                # The router reads these: only a model_provider card sets them.
                raise ValueError("owner_action_secret_name_reserved")
            return self
        # A connecting card: the server sets its fields; the agent gives the details.
        needs: set[str] = {
            "mcp_server": set[str]() if self.service == "x" else {"name"},
            "brave_search": set[str](),
            "news_feed": {"name"},
            "economic_calendar": {"name"},
            "model_provider": {"name"},
        }[self.target]
        optional = {"name"} if self.target in {"mcp_server", "brave_search"} else set[str]()
        allowed = needs | optional
        given = {"name"} if self.name is not None else set[str]()
        if (
            self.label is not None
            or self.secret_fields is not None
            or not needs <= given <= allowed
            or (self.service is not None and self.target != "mcp_server")
            or (self.target == "model_provider" and self.name not in get_args(ProviderId))
        ):
            raise ValueError("owner_action_fields_invalid")
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


class OwnerActionDecision(Contract):
    """The owner's tap. ``outcome`` answers a Settle Uncertain Operation card (exactly
    executed, not executed or unknown). A Secret card's values never come here: the card
    has its own route. There is no grant card and no passkey on this decision.
    """

    decision: Literal["confirm", "cancel"]
    # The Mandate card: the mode its button showed at the moment of the tap.
    trading_mode: TradingMode | None = None
    outcome: AttestedOutcome | None = None
