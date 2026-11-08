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

from .account_authority import AuthorityAction
from .devices import DeviceProof
from .domain import Contract

OwnerActionKind = Literal[
    "resume_trading",
    "lift_restriction",
    "resolve_operation",
    "set_account_limits",
    "grant_authority",
]
GrantDuration = Literal["until_stopped", "12h", "24h", "7d"]
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

    @model_validator(mode="after")
    def fields_for_kind(self) -> "OwnerActionProposal":
        limits = bool(
            self.set_limits or self.remove_limits or self.currency or self.trading_day_timezone
        )
        grant = any(
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
            )
        )
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


class GrantDraft(Contract):
    """A grant card's stored, server-resolved draft. The signed envelope is built only
    from this and the owner's own choices on the card, never from model text."""

    agent_id: str = Field(min_length=1, max_length=36)
    account_id: str = Field(min_length=1, max_length=120)
    symbol_scope: Literal["selected", "account"]
    symbols: list[str] = Field(default_factory=list[str], max_length=100)
    actions: list[AuthorityAction] = Field(min_length=1, max_length=10)
    duration: GrantDuration = "until_stopped"
    allow_manual_positions: bool = False
    daily_loss: DailyLossDraft | None = None

    @model_validator(mode="after")
    def scope(self) -> "GrantDraft":
        if (self.symbol_scope == "selected") != bool(self.symbols):
            raise ValueError("authority_exact_symbols_required")
        return self


class OwnerActionChallenge(Contract):
    """The owner's choice on a grant card that changes what is signed: including the
    positions the owner opened manually. Sent with the passkey challenge."""

    allow_manual_positions: bool | None = None


class OwnerActionDecision(Contract):
    """The owner's tap. ``outcome`` answers a resolve card; ``proof`` is the passkey
    assertion a widening card requires (obtained from the card's challenge).

    A grant card's own choices narrow or widen nothing that needs another signature:
    leaving the account without the suggested daily loss limit (``money_limit``
    "none"), resuming new trading, and stopping other agents' grants on that market.
    """

    decision: Literal["confirm", "cancel"]
    outcome: AttestedOutcome | None = None
    note: str | None = Field(default=None, max_length=2000)
    broker_reference: str | None = Field(default=None, max_length=200)
    proof: DeviceProof | None = None
    money_limit: Literal["apply", "none"] = "apply"
    resume_trading: bool = False
    stop_authorities: list[str] = Field(default_factory=list[str], max_length=20)
