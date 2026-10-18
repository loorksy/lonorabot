"""Operational recovery facts; never hidden reasoning or financial authority."""

from typing import Literal

from pydantic import Field

from .domain import Contract

FailureCategory = Literal[
    "invalid_tool_arguments",
    "result_too_large",
    "temporary_unavailable",
    "version_conflict",
    "stale_state",
    "authorization_required",
    "permission_denied",
    "not_configured",
    "not_found",
    "health_blocked",
    "ambiguous_mutation",
    "terminal_domain_failure",
]


class ToolRecovery(Contract):
    category: FailureCategory
    next_action: str = Field(min_length=1, max_length=80)
    safe_to_retry: bool = False
    schema_tool: Literal["tool_environment"] = "tool_environment"
    attempt: int = Field(default=0, ge=0)
    retry_exhausted: bool = False
