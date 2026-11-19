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
# Financial statuses whose outcome is not yet known (lonora_contracts.trading lifecycle).
IN_FLIGHT = frozenset({"ambiguous", "submitted", "reserved"})
# Settled without broker confirmation (owner attestation or a vanished/changed target):
# terminal, so never retried or resent, but not evidence that the requested effect holds.
SETTLED_UNCONFIRMED = "resolved"


class ToolRetryScheduled(Exception):
    """Release this worker; the existing Run claimant observes the durable deadline."""


def route_key(call: ToolCall) -> str:
    return request_hash({"tool": call.name, "arguments": call.arguments})


ERROR_CLASSES: dict[str, str] = {
    "invalid_tool_arguments": "input",
    "result_too_large": "input",
    "not_found": "resolution",
    "version_conflict": "resolution",
    "stale_state": "resolution",
    "temporary_unavailable": "connection",
    "authorization_required": "permission",
    "permission_denied": "permission",
    "not_configured": "provider",
    "health_blocked": "provider",
    "ambiguous_mutation": "provider",
}


# An order the contract cannot take as written: the arguments are wrong, nothing else is.
ORDER_ARGUMENT_CODES = frozenset(
    {
        "volume_out_of_range",
        "volume_step_mismatch",
        "price_tick_mismatch",
        "position_volume_exceeded",
        "position_remaining_volume_invalid",
        # A size request the account or its currency cannot answer as asked.
        "position_sizing_below_minimum",
        "position_sizing_account_mismatch",
        "position_sizing_currency_mismatch",
    }
)

# What the model does next when a failure brings no hint of its own, by recovery category.
RECOVERY_HINTS: dict[FailureCategory, str] = {
    "invalid_tool_arguments": "The arguments are not acceptable as written. Correct them "
    "and call again.",
    "result_too_large": "The result is too large to read at once. Ask for less: a "
    "narrower range, fewer items or a filter.",
    "temporary_unavailable": "A temporary failure of the connection. The same read can be "
    "tried again; do not report it to the owner as a refusal.",
    "version_conflict": "What this was based on has changed since it was read. Read the "
    "current state again, then decide from it.",
    "stale_state": "The evidence is too old to act on. Read it fresh, then decide from it.",
    "authorization_required": "Only the owner can allow this. Say in one plain line what "
    "needs their approval; do not look for another way to do the same thing.",
    "permission_denied": "A rule of the owner's or the account's forbids this. Do not look "
    "for another way to do the same thing: tell the owner what is needed, or raise the "
    "card for it.",
    "not_configured": "This is not set up yet, so it cannot run. Take another authorized "
    "route to the same result, or tell the owner what has to be connected.",
    "not_found": "What the call named was not found as written. Read what exists, then "
    "call again with the exact name; ask the owner only if several fit.",
    "health_blocked": "The state of the account or the system blocks this for now, not "
    "the request itself. Do not repeat it or route around it; say what is blocked.",
    "ambiguous_mutation": "The outcome is not known: this may or may not have taken "
    "effect. Do not send it again. Read the current state to learn what happened, and "
    "until then say it is being confirmed, never that it failed or went through.",
    "terminal_domain_failure": "This did not go through, for the reason given. Do not "
    "repeat it unchanged. A rule or a decision of the owner's is respected, not routed "
    "around; anything else may have another route to the same goal. Otherwise say plainly "
    "what could not be done.",
}
# A read that kept failing is not offered again in this turn.
RETRY_EXHAUSTED_HINT = (
    "This kept failing and is not tried again now. Take another route to the same "
    "information, or say plainly that it could not be read at the moment."
)
# The connection failed on a call that is not a read: it is not repeated by itself.
UNSENT_HINT = (
    "The connection failed before this was carried out. Do not call it again by itself: "
    "say that it could not be done now."
)


# A refusal classify() does not name, by the class the tool itself gave it.
CLASS_CATEGORIES: dict[str, tuple[FailureCategory, str]] = {
    "input": ("invalid_tool_arguments", "correct_arguments"),
    "resolution": ("not_found", "inspect_existing_state"),
    "connection": ("temporary_unavailable", "inspect_health"),
    "permission": ("permission_denied", "respect_scope"),
}


def _by_status(code: str, status: int) -> tuple[FailureCategory, str] | None:
    """The category of a refusal classify() does not name, from the status its tool raised.

    Only the families that hold for nearly every code of a status are read this way; a
    state conflict (most of 409) says nothing a model can act on and stays as it was.
    """
    if code.endswith("_unavailable") or code.startswith("mcp_schema_"):
        # The source's own trouble, whatever status carried it.
        return None
    if status in {401, 403}:
        # An action that failed in the browser is not a rule.
        return None if code == "browser_action_failed" else ("permission_denied", "respect_scope")
    if status in {400, 413, 422}:
        return "invalid_tool_arguments", "correct_arguments"
    if status != 409:
        return None
    if code.endswith("_confirmation_required"):
        return "authorization_required", "request_owner_authorization"
    if code.endswith("_reconciliation_required"):
        return "health_blocked", "wait_for_authoritative_recovery"
    if code.startswith(("account_authority_", "work_paused")) or code.endswith(
        ("_forbidden", "_paused")
    ):
        # The mandate's own terms, or a pause someone set. A count that is full
        # (helpers, pins, retries) is not a rule and stays as it was.
        return "permission_denied", "respect_scope"
    if code.endswith(("_wrong_side", "_stops_level")):
        return "invalid_tool_arguments", "correct_arguments"
    return None


def error_class(code: str, category: str) -> str:
    """input | resolution | connection | permission | provider | internal."""
    if category in ERROR_CLASSES:
        return ERROR_CLASSES[category]
    return "provider" if code.startswith("broker_") else "internal"


def classify(code: str, tool: Tool | None, status: int | None = None) -> dict[str, Any]:
    category: FailureCategory = "terminal_domain_failure"
    action = "alternate_route"
    if code == "tool_arguments_invalid":
        category, action = "invalid_tool_arguments", "inspect_schema_and_repair"
    elif code in ORDER_ARGUMENT_CODES:
        category, action = "invalid_tool_arguments", "correct_arguments"
    elif code == "tool_result_too_large":
        category, action = "result_too_large", "narrow_query"
    elif code in AMBIGUOUS:
        category, action = "ambiguous_mutation", "reconcile_before_any_resend"
    elif code in TRANSIENT_READ_CODES:
        category, action = "temporary_unavailable", "inspect_health"
    elif code in {"version_conflict", "stale_state"}:
        category, action = "version_conflict", "reload_authoritative_state"
    elif code in {"quote_stale", "market_data_stale", "market_evidence_stale", "stale_evidence"}:
        category, action = "stale_state", "refresh_evidence"
    elif code in {
        "approval_required",
        "trade_approval_required",
        "device_registration_required",
        "device_authorization_required",
    }:
        category, action = "authorization_required", "request_owner_authorization"
    elif code in {
        "tool_not_allowed",
        "agent_market_binding_mismatch",
        "agent_trading_account_mismatch",
        "agent_trading_symbol_mismatch",
        "financial_authority_required",
        # The owner said no to this card, or the agent's level does not trade.
        "trade_approval_rejected",
        "agent_analysis_only",
        "shadow_execution_forbidden",
        # Supervision never silences the owner's entry point or sheds its own oversight.
        "supervision_personal_agent",
        "supervision_revoke_own_oversight",
        # The owner or a supervisor paused this agent.
        "agent_paused",
        # One Run creates so many agents and no more.
        "agent_create_run_limit",
        # Rules that no corrected argument gets past.
        "trusted_source_write_blocked",
        "ui_submit_disabled",
        "memory_disclosure_refused",
    }:
        category, action = "permission_denied", "respect_scope"
    elif code.endswith("_unconfigured") or code in {
        "model_not_configured",
        "search_not_configured",
        "research_provider_not_configured",
    }:
        category, action = "not_configured", "inspect_authorized_alternative"
    elif code in {"symbol_not_found", "symbol_ambiguous"}:
        # The result carries the account's candidates and a hint: act on them.
        category, action = "not_found", "follow_hint"
    elif code.endswith("_not_found"):
        category, action = "not_found", "inspect_existing_state"
    elif code in {
        "broker_reconciliation_pending",
        "market_health_blocked",
    }:
        category, action = "health_blocked", "wait_for_authoritative_recovery"
    elif status is not None and not code.startswith("broker_"):
        category, action = _by_status(code, status) or (category, action)
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


def expire_read_routes(state: dict[str, Any]) -> None:
    """Forget settled read routes at real owner input or an external wake.

    An exhausted read (for example a quote while the market was closed) would
    otherwise stay refused for the rest of a long-lived Run. Only records known
    to be read-only and not ambiguous are dropped; an uncertain effect, and any
    record written before the flag existed, keeps blocking until reconciled.
    """
    environment = state.get("environment")
    if not isinstance(environment, dict):
        return
    routes = cast(dict[str, Any], environment).get("routes")
    if not isinstance(routes, dict):
        return
    for key, record in list(cast(dict[str, Any], routes).items()):
        if (
            isinstance(record, dict)
            and cast(dict[str, Any], record).get("read_only") is True
            and not cast(dict[str, Any], record).get("ambiguous")
        ):
            del routes[key]


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
    # The status a refusal was raised with (tool_dispatch) is read here and goes no further.
    status = result.pop("http_status", None)
    # A handler's own sentence of guidance is the hint; `recovery` is the runtime's block.
    authored = result.get("recovery")
    if isinstance(authored, str):
        del result["recovery"]
        result.setdefault("hint", authored)
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
        result.get("status") in IN_FLIGHT
        or nested.get("status") in IN_FLIGHT
        or code in AMBIGUOUS
        or any(
            item.get("status") in IN_FLIGHT or item.get("code") in AMBIGUOUS for item in outcomes
        )
    )
    # A read that returns the record of a failed operation has itself succeeded.
    settled_failure = result.get("status") in {"failed", "rejected"} and not (
        tool and tool.read_only
    )
    failed = result.get("ok") is False or uncertain or settled_failure
    unconfirmed = not failed and (
        result.get("status") == SETTLED_UNCONFIRMED
        or nested.get("status") == SETTLED_UNCONFIRMED
        or any(item.get("status") == SETTLED_UNCONFIRMED for item in outcomes)
    )
    failures = int(previous.get("failures", 0)) + 1 if failed else 0
    record = {
        "tool": call.name,
        "call_id": call.id,
        "origin_call_id": previous.get("origin_call_id", call.id)
        if previous.get("ambiguous")
        else call.id,
        "code": code if failed else "operation_resolved_unconfirmed" if unconfirmed else None,
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
        # Lets a new review epoch expire exhausted reads, never uncertain effects.
        "read_only": bool(tool and tool.read_only),
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
        recovery = classify(
            "broker_result_ambiguous" if uncertain else code,
            tool,
            None if uncertain or not isinstance(status, int) else status,
        )
        if recovery["category"] == "terminal_domain_failure":
            # The class a tool wrote decides what its refusal means.
            authored_class = result.get("class")
            if isinstance(authored_class, str) and authored_class in CLASS_CATEGORIES:
                recovery["category"], recovery["next_action"] = CLASS_CATEGORIES[authored_class]
        if recovery["category"] == "not_found" and result.get("candidates"):
            # The result names what exists: the next call is in it.
            recovery["next_action"] = "follow_hint"
        recovery["attempt"] = failures
        if failures >= 3 and recovery["safe_to_retry"]:
            recovery["safe_to_retry"] = False
            recovery["next_action"] = "alternate_route_or_wait"
            recovery["retry_exhausted"] = True
        elif isinstance(authored, dict) and "category" not in authored:
            # The next step a handler named itself is kept.
            named = cast(dict[str, Any], authored).get("next_action")
            if isinstance(named, str):
                recovery["next_action"] = named
        result["recovery"] = recovery
        if settled_failure:
            # A refused or failed operation is not a success of the call.
            result["ok"] = False
        # The unified error contract; a tool's own class, retryable and hint are kept.
        result.setdefault("class", error_class(code, recovery["category"]))
        result.setdefault("retryable", recovery["safe_to_retry"])
        if recovery["retry_exhausted"]:
            hint = RETRY_EXHAUSTED_HINT
        elif recovery["category"] == "temporary_unavailable" and not recovery["safe_to_retry"]:
            hint = UNSENT_HINT
        else:
            hint = RECOVERY_HINTS[recovery["category"]]
        result.setdefault("hint", hint)
    elif unconfirmed:
        # Not a success to build on: read the account again before any next decision.
        result["recovery"] = ToolRecovery(
            category="stale_state", next_action="reload_authoritative_state"
        ).model_dump(mode="json")
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
