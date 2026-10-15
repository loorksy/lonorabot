"""Visibility metadata is descriptive; it never grants execution authority."""

from typing import Literal

from .domain import Contract

AgentRole = Literal["personal", "specialist", "legacy"]


class AgentScope(Contract):
    role: AgentRole
    account_id: str | None = None
    broker_symbol: str | None = None
    visibility: Literal["owner_accounts", "bound_market", "legacy"]
    execution_authority: Literal["existing_server_controls"] = "existing_server_controls"
