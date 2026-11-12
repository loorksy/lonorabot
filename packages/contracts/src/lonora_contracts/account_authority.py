"""Explicit, signed account delegation."""

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, get_args

from pydantic import Field, model_validator

from .domain import Contract, utcnow

AuthorityAction = Literal[
    "buy",
    "sell",
    "buy_limit",
    "sell_limit",
    "buy_stop",
    "sell_stop",
    "close_position",
    "modify_position",
    "cancel_order",
    "modify_order",
]
# Every action a grant can allow: open, close fully or partly, pending orders, changing
# stop loss and take profit, cancelling and modifying orders.
ALL_AUTHORITY_ACTIONS: tuple[AuthorityAction, ...] = get_args(AuthorityAction)
AUTHORITY_CAPS = (
    "maximum_order_volume",
    "maximum_symbol_volume",
    "maximum_positions",
    "maximum_pending_orders",
    "maximum_actions",
    "minimum_equity",
)


def full_delegation(envelope: Mapping[str, Any]) -> bool:
    """Whether a grant (an envelope, or its stored JSON) is Full delegation: full
    management of every pair on its account, every action and the owner's own
    positions, with no expiry and no cap of its own. The account's money limits and the
    owner's pauses still bind it; nothing here is authority."""
    return (
        envelope.get("management_mode") == "full"
        and envelope.get("symbol_scope") == "account"
        and set(envelope.get("actions") or ()) == set(ALL_AUTHORITY_ACTIONS)
        and envelope.get("valid_until") is None
        and envelope.get("allow_manual_positions") is True
        and all(envelope.get(name) is None for name in AUTHORITY_CAPS)
    )


class AccountAuthorityProposal(Contract):
    thread_id: str = Field(min_length=1, max_length=36)
    account_id: str = Field(min_length=1, max_length=120)
    management_mode: Literal["bounded", "full"] = "bounded"
    symbol_scope: Literal["selected", "account"] = "selected"
    symbols: list[str] = Field(default_factory=list, max_length=100)
    actions: list[AuthorityAction] = Field(min_length=1, max_length=10)
    maximum_order_volume: Decimal | None = Field(default=None, gt=0)
    maximum_symbol_volume: Decimal | None = Field(default=None, gt=0)
    maximum_positions: int | None = Field(default=None, ge=1, le=100)
    maximum_pending_orders: int | None = Field(default=None, ge=0, le=100)
    maximum_actions: int | None = Field(default=None, ge=1, le=10000)
    minimum_equity: Decimal | None = Field(default=None, gt=0)
    valid_until: datetime | None = None
    allow_manual_positions: bool = False

    @model_validator(mode="after")
    def bounded_scope(self) -> "AccountAuthorityProposal":
        if self.valid_until is not None and self.valid_until.tzinfo is None:
            raise ValueError("authority_expiry_timezone_required")
        if self.symbol_scope == "selected" and not self.symbols:
            raise ValueError("authority_exact_symbols_required")
        if self.symbol_scope == "account" and (self.symbols or self.management_mode != "full"):
            raise ValueError("authority_account_scope_requires_full_management")
        if self.management_mode == "bounded" and any(
            getattr(self, field) is None
            for field in (
                "maximum_order_volume",
                "maximum_symbol_volume",
                "maximum_positions",
                "maximum_pending_orders",
                "maximum_actions",
                "minimum_equity",
                "valid_until",
            )
        ):
            raise ValueError("authority_bounded_limits_required")
        if any(not item or len(item) > 80 or item.strip() != item for item in self.symbols):
            raise ValueError("authority_exact_symbols_required")
        if len(set(self.symbols)) != len(self.symbols) or len(set(self.actions)) != len(
            self.actions
        ):
            raise ValueError("authority_duplicate_scope")
        if (
            self.maximum_order_volume is not None
            and self.maximum_symbol_volume is not None
            and self.maximum_order_volume > self.maximum_symbol_volume
        ):
            raise ValueError("authority_order_volume_exceeds_symbol_limit")
        return self

    def permits_symbol(self, symbol: str) -> bool:
        return self.symbol_scope == "account" or symbol in self.symbols


class AccountAuthorityEnvelope(AccountAuthorityProposal):
    owner_id: str
    agent_id: str
    execution_mode: Literal["live"] = "live"
    schema_version: Literal[1, 2] = 1

    @model_validator(mode="after")
    def versioned_authority(self) -> "AccountAuthorityEnvelope":
        if self.schema_version == 1 and (
            self.management_mode != "bounded" or self.symbol_scope != "selected"
        ):
            raise ValueError("authority_full_management_requires_v2")
        return self


def require_future_expiry(value: datetime) -> None:
    if value <= utcnow():
        raise ValueError("authority_expired")
