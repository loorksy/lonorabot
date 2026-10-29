"""Owner-selected approval behavior and non-executable customization drafts."""

from typing import Literal

from pydantic import Field

from .account_authority import AuthorityAction
from .domain import Contract

PermissionLevel = Literal["analysis", "supervised", "autonomous"]
LowerPermissionLevel = Literal["analysis", "supervised"]
PermissionStatus = Literal[
    "analysis",
    "supervised",
    "autonomous",
    "awaiting_authorization",
    "authorization_expired",
    "autonomous_stopped",
]


class CustomizationLimits(Contract):
    maximum_order_volume: str = Field(default="", max_length=80)
    maximum_symbol_volume: str = Field(default="", max_length=80)
    maximum_positions: str = Field(default="", max_length=80)
    maximum_pending_orders: str = Field(default="", max_length=80)
    maximum_actions: str = Field(default="", max_length=80)
    minimum_equity: str = Field(default="", max_length=80)


class PermissionCustomization(Contract):
    # Drafts preserve partially edited values. They never constitute a proposal,
    # so an empty action set/account or invalid numeric text is safe to save.
    account_id: str = Field(default="", max_length=120)
    symbol_scope: Literal["selected", "account"] = "selected"
    symbols: list[str] = Field(default_factory=list, max_length=100)
    actions: list[AuthorityAction] = Field(
        default_factory=lambda: list[AuthorityAction](), max_length=10
    )
    limits: CustomizationLimits = Field(default_factory=CustomizationLimits)
    duration: Literal["until_stopped", "12h", "24h", "7d"] = "until_stopped"
    allow_manual_positions: bool = True


class PermissionRecord(Contract):
    owner_id: str
    agent_id: str
    revision: int = Field(default=0, ge=0)
    fallback_level: LowerPermissionLevel = "analysis"
    customization: PermissionCustomization | None = None


class PermissionChange(Contract):
    level: LowerPermissionLevel
    expected_revision: int = Field(ge=0)


class PermissionCustomizationChange(Contract):
    expected_revision: int = Field(ge=0)
    customization: PermissionCustomization
