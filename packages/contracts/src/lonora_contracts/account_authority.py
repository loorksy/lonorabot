"""Explicit, signed account delegation; independent of a predeclared Goal plan."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

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


class AccountAuthorityProposal(Contract):
    thread_id: str = Field(min_length=1, max_length=36)
    account_id: str = Field(min_length=1, max_length=120)
    symbols: list[str] = Field(min_length=1, max_length=100)
    actions: list[AuthorityAction] = Field(min_length=1, max_length=10)
    maximum_order_volume: Decimal = Field(gt=0)
    maximum_symbol_volume: Decimal = Field(gt=0)
    maximum_positions: int = Field(ge=1, le=100)
    maximum_pending_orders: int = Field(ge=0, le=100)
    maximum_actions: int = Field(ge=1, le=10000)
    minimum_equity: Decimal = Field(gt=0)
    valid_until: datetime
    allow_manual_positions: bool = False

    @model_validator(mode="after")
    def bounded_scope(self) -> "AccountAuthorityProposal":
        if self.valid_until.tzinfo is None:
            raise ValueError("authority_expiry_timezone_required")
        if any(not item or len(item) > 80 or item.strip() != item for item in self.symbols):
            raise ValueError("authority_exact_symbols_required")
        if len(set(self.symbols)) != len(self.symbols) or len(set(self.actions)) != len(
            self.actions
        ):
            raise ValueError("authority_duplicate_scope")
        if self.maximum_order_volume > self.maximum_symbol_volume:
            raise ValueError("authority_order_volume_exceeds_symbol_limit")
        return self


class AccountAuthorityEnvelope(AccountAuthorityProposal):
    owner_id: str
    agent_id: str
    execution_mode: Literal["live"] = "live"
    schema_version: Literal[1] = 1


def require_future_expiry(value: datetime) -> None:
    if value <= utcnow():
        raise ValueError("authority_expired")
