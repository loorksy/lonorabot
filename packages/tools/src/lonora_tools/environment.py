"""Safe, bounded inspection of the actual registry, never a second tool registry."""

from typing import Any

from lonora_contracts.domain import Contract
from lonora_core.runtime_failure import TRANSIENT_READ_CODES
from pydantic import Field


class EnvironmentInput(Contract):
    tool_name: str | None = Field(default=None, min_length=1, max_length=100)
    query: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
        description="Search available tool names/descriptions using concise catalog terms. Use English terms for the first-party catalog, or inspect an exact tool_name. Search grants no authority.",
    )
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=20, ge=1, le=40)


def recovery_metadata(read_only: bool, financial: bool) -> dict[str, Any]:
    return {
        "side_effect": "read_only" if read_only else "financial" if financial else "mutating",
        "safe_automatic_retry": read_only,
        "maximum_automatic_retries": 2 if read_only else 0,
        "reconciliation_after_uncertainty": not read_only,
        "scope": "current_owner_agent_and_run",
        "authority": "server_validated",
        "result_limit_chars": 120000,
        "common_error_codes": [
            "tool_arguments_invalid",
            "tool_result_too_large",
            "tool_not_allowed",
            *sorted(TRANSIENT_READ_CODES),
        ]
        if read_only
        else [
            "tool_arguments_invalid",
            "version_conflict",
            "broker_result_ambiguous" if financial else "tool_execution_uncertain",
        ],
        "operation_identity": "server_owned" if financial else "handler_defined",
        "output_contract": "object; the ToolLoop adds ok/code/recovery metadata",
    }
