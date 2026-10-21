"""Typed operational observations in the existing fenced Run checkpoint.

No model reasoning, raw arguments or exception text is stored here. External
effects remain owned by their existing receipts/journals, never this summary.
"""

from datetime import datetime, timedelta
from typing import Any, cast

from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_contracts.tool_environment import FailureCategory, ToolRecovery
from lonora_core.runtime_failure import TRANSIENT_READ_CODES
from lonora_session.idempotency import request_hash
from lonora_tools.base import Tool

AMBIGUOUS = frozenset(
    {"broker_result_ambiguous", "operation_ambiguous", "tool_execution_uncertain"}
)


class ToolRetryScheduled(Exception):
    """Release this worker; the existing Run claimant observes the durable deadline."""


def route_key(call: ToolCall) -> str:
    return request_hash({"tool": call.name, "arguments": call.arguments})


def classify(code: str, tool: Tool | None) -> dict[str, Any]:
    category: FailureCategory = "terminal_domain_failure"
    action = "alternate_route"
    if code == "tool_arguments_invalid":
        category, action = "invalid_tool_arguments", "inspect_schema_and_repair"
    elif code == "tool_result_too_large":
        category, action = "result_too_large", "narrow_query"
    elif code in AMBIGUOUS:
        category, action = "ambiguous_mutation", "reconcile_before_any_resend"
    elif code in TRANSIENT_READ_CODES:
        category, action = "temporary_unavailable", "inspect_health"
    elif code in {"version_conflict", "stale_state", "workspace_revision_conflict"}:
        category, action = "version_conflict", "reload_authoritative_state"
    elif code in {"quote_stale", "market_data_stale", "market_evidence_stale", "stale_evidence"}:
        category, action = "stale_state", "refresh_evidence"
    elif code in {
        "approval_required",
        "device_registration_required",
        "device_authorization_required",
    }:
        category, action = "authorization_required", "request_owner_authorization"
    elif code in {
        "tool_not_allowed",
        "agent_market_binding_mismatch",
        "financial_authority_required",
    }:
        category, action = "permission_denied", "respect_scope"
    elif code.endswith("_unconfigured") or code in {
        "model_not_configured",
        "search_not_configured",
    }:
        category, action = "not_configured", "inspect_authorized_alternative"
    elif code.endswith("_not_found"):
        category, action = "not_found", "inspect_existing_state"
    elif code in {
        "broker_reconciliation_pending",
        "market_health_blocked",
        "trading_disabled",
        "emergency_stop",
    }:
        category, action = "health_blocked", "wait_for_authoritative_recovery"
    return ToolRecovery(
        category=category,
        next_action=action,
        safe_to_retry=bool(tool and tool.read_only and code in TRANSIENT_READ_CODES),
    ).model_dump(mode="json")


def environment_state(state: dict[str, Any]) -> dict[str, Any]:
    environment = state.setdefault("environment", {})
    environment.setdefault("version", 1)
    environment.setdefault("routes", {})
    environment.setdefault("recent", [])
    return environment


def blocked_route(state: dict[str, Any], call: ToolCall) -> dict[str, Any] | None:
    record = environment_state(state)["routes"].get(route_key(call), {})
    if record.get("ambiguous") or record.get("failures", 0) >= 3:
        return record
    return None


def observe(
    state: dict[str, Any], call: ToolCall, tool: Tool | None, result: dict[str, Any]
) -> dict[str, Any]:
    env = environment_state(state)
    key = route_key(call)
    routes = env["routes"]
    previous = routes.get(key, {})
    nested_value = result.get("result")
    nested: dict[str, Any] = (
        cast(dict[str, Any], nested_value) if isinstance(nested_value, dict) else {}
    )
    code = str(result.get("code") or nested.get("code") or "tool_failed")
    raw_outcomes = result.get("results")
    outcomes = (
        [
            cast(dict[str, Any], item)
            for item in cast(list[Any], raw_outcomes)
            if isinstance(item, dict)
        ]
        if isinstance(raw_outcomes, list)
        else []
    )
    uncertain = (
        result.get("status") in {"ambiguous", "submitted"}
        or nested.get("status") in {"ambiguous", "submitted"}
        or code in AMBIGUOUS
        or any(
            item.get("status") in {"ambiguous", "submitted"} or item.get("code") in AMBIGUOUS
            for item in outcomes
        )
    )
    failed = (
        result.get("ok") is False or uncertain or result.get("status") in {"failed", "rejected"}
    )
    failures = int(previous.get("failures", 0)) + 1 if failed else 0
    record = {
        "tool": call.name,
        "call_id": call.id,
        "origin_call_id": previous.get("origin_call_id", call.id)
        if previous.get("ambiguous")
        else call.id,
        "code": code if failed else None,
        "failures": failures,
        "ambiguous": uncertain or bool(previous.get("ambiguous")),
        "receipt_replay": previous.get("receipt_replay", False)
        if previous.get("ambiguous")
        else bool(
            tool
            and tool.replay_safe
            and (call.id not in env.get("legacy_pending", []) or tool.legacy_replay_safe)
        ),
        "observed_at": utcnow().isoformat(),
    }
    routes.pop(key, None)
    routes[key] = record
    # Keep unresolved effects even when read routes are rotated out.
    while len(routes) > 32:
        removable = next((k for k, value in routes.items() if not value.get("ambiguous")), None)
        if removable is None:
            break
        del routes[removable]
    env["recent"] = [*env.get("recent", []), record][-12:]
    env["phase"] = "recovering" if failed else "working"
    if failed:
        recovery = classify("broker_result_ambiguous" if uncertain else code, tool)
        recovery["attempt"] = failures
        if failures >= 3 and recovery["safe_to_retry"]:
            recovery["safe_to_retry"] = False
            recovery["next_action"] = "alternate_route_or_wait"
            recovery["retry_exhausted"] = True
        result["recovery"] = recovery
    return record


def schedule_retry(state: dict[str, Any], call: ToolCall, attempt: int) -> None:
    environment_state(state)["retry"] = {
        "call_id": call.id,
        "not_before": (utcnow() + timedelta(seconds=2**attempt)).isoformat(),
        "attempt": attempt,
    }


def retry_pending(state: dict[str, Any], call: ToolCall) -> bool:
    retry = environment_state(state).get("retry", {})
    return (
        retry.get("call_id") == call.id and datetime.fromisoformat(retry["not_before"]) > utcnow()
    )


def bounded_result(result: dict[str, Any]) -> dict[str, Any]:
    """Omitted data is not failure of an effect which already happened."""
    bounded: dict[str, Any] = {
        "ok": result.get("ok") is True,
        "context_notice": "tool_result_too_large",
        "result_omitted": True,
        "recovery": {
            "category": "result_too_large",
            "next_action": "narrow_query",
            "schema_tool": "tool_environment",
        },
    }
    for field in (
        "code",
        "status",
        "operation_id",
        "broker_reference",
        "artifact_id",
        "approval_id",
        "chart_id",
        "id",
        "symbol",
    ):
        value = result.get(field)
        if isinstance(value, str) and len(value) <= 128:
            bounded[field] = value
    recovery = result.get("recovery")
    if (
        isinstance(recovery, dict)
        and cast(dict[str, Any], recovery).get("category") == "ambiguous_mutation"
    ):
        # Batch uncertainty can lie beyond the bounded first twenty entries.
        bounded["status"] = "ambiguous"
        bounded["recovery"] = {
            "category": "ambiguous_mutation",
            "next_action": "reconcile_before_any_resend",
            "safe_to_retry": False,
        }
    nested = result.get("result")
    if isinstance(nested, dict):
        bounded["result"] = {
            key: value
            for key in ("operation_id", "status", "code", "broker_reference")
            if isinstance(value := cast(dict[str, Any], nested).get(key), str) and len(value) <= 128
        }
    outcomes = result.get("results")
    if isinstance(outcomes, list):
        entries = cast(list[Any], outcomes)
        summaries: list[dict[str, str]] = []
        for item in entries[:20]:
            if not isinstance(item, dict):
                continue
            record = cast(dict[str, Any], item)
            summaries.append(
                {
                    key: value
                    for key in ("operation_id", "status", "code", "broker_reference")
                    if isinstance(value := record.get(key), str) and len(value) <= 128
                }
            )
        bounded["results"] = summaries
        bounded["result_count"] = len(entries)
        bounded["results_truncated"] = len(entries) > 20
    return bounded
