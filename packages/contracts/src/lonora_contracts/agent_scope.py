"""Visibility metadata is descriptive; it never grants execution authority."""

from typing import Literal

from .domain import Contract

AgentRole = Literal["personal", "general", "specialist", "delegated", "legacy"]


class AgentScope(Contract):
    mode: Literal["fixed_market", "flexible"] = "fixed_market"
    role: AgentRole
    account_id: str | None = None
    broker_symbol: str | None = None
    visibility: Literal["owner_accounts", "bound_market", "delegated_research", "legacy"]
    execution_authority: Literal["existing_server_controls", "none"] = "existing_server_controls"
