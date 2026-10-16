"""Typed tool observations for the existing Agent loop.

A tool failure is an observation about the environment. It does not by itself
finish the owner's goal, and it never grants financial authority.
"""

import hashlib
import json
from typing import Any, Literal, cast

Classification = Literal[
    "invalid_input",
    "invalid_tool_arguments",
    "result_too_large",
    "temporary_unavailable",
    "connection_failure",
    "stale_state",
    "version_conflict",
    "missing_capability",
    "not_configured",
    "not_found",
    "health_blocked",
    "authorization_required",
    "permission_denied",
    "external_wait",
    "ambiguous_mutation",
    "terminal_domain_failure",
]
Recovery = Literal[
    "repair",
    "narrow",
    "retry_read",
    "reconcile",
    "reload",
    "wait",
    "change_strategy",
    "ask_owner",
    "terminal",
]
Activity = Literal[
    "working",
    "gathering",
    "waiting_approval",
    "waiting_market",
    "recovering_broker",
    "consulting",
    "paused",
    "completed",
]

FINANCIAL_TOOLS = frozenset({"trade_execute", "trade_close_positions", "goal_step_execute"})
ROUTE_LIMIT = 8
REPEAT_LIMIT = 2

_EXACT: dict[str, tuple[Classification, Recovery, bool]] = {
    "tool_arguments_invalid": ("invalid_tool_arguments", "repair", False),
    "tool_result_too_large": ("result_too_large", "narrow", False),
    "broker_connection_timeout": ("connection_failure", "retry_read", False),
    "broker_connection_unavailable": ("connection_failure", "retry_read", False),
    "broker_candles_timeout": ("connection_failure", "retry_read", False),
    "market_quote_unavailable": ("temporary_unavailable", "retry_read", False),
    "watch_candles_unavailable": ("temporary_unavailable", "retry_read", False),
    "relationship_history_timeout": ("temporary_unavailable", "retry_read", False),
    "version_conflict": ("version_conflict", "reload", False),
    "idempotency_conflict": ("version_conflict", "reload", False),
    "broker_symbol_not_found": ("not_found", "change_strategy", False),
    "chart_indicator_not_found": ("not_found", "change_strategy", False),
    "watch_indicator_unavailable": ("missing_capability", "change_strategy", False),
    "calendar_integration_unavailable": ("missing_capability", "change_strategy", False),
    "shadow_monetary_pnl_unavailable": ("missing_capability", "change_strategy", False),
    "model_not_configured": ("not_configured", "ask_owner", True),
    "broker_unconfigured": ("not_configured", "ask_owner", True),
    "model_credentials_rejected": ("not_configured", "ask_owner", True),
    "tool_not_allowed": ("permission_denied", "terminal", False),
    "observe_only_execution_forbidden": ("permission_denied", "terminal", False),
    "shadow_execution_forbidden": ("permission_denied", "terminal", False),
    "goal_delegated_trade_forbidden": ("permission_denied", "terminal", False),
    "unauthorized": ("authorization_required", "ask_owner", True),
    "device_authorization_required": ("authorization_required", "ask_owner", True),
    "device_registration_required": ("authorization_required", "ask_owner", True),
    "broker_reconciliation_required": ("ambiguous_mutation", "reconcile", False),
    "operation_send_already_authorized": ("ambiguous_mutation", "reconcile", False),
    "operation_in_progress": ("ambiguous_mutation", "reconcile", False),
    "broker_disabled": ("health_blocked", "wait", False),
    "trading_disabled": ("health_blocked", "ask_owner", True),
    "emergency_stop": ("health_blocked", "ask_owner", True),
    "route_exhausted": ("terminal_domain_failure", "change_strategy", False),
    "financial_retry_blocked": ("ambiguous_mutation", "reconcile", False),
}

_GUIDANCE: dict[Recovery, str] = {
    "repair": (
        "Inspect schema_fields and issues, correct the arguments, and retry in this run. "
        "Do not ask the owner to operate the tool."
    ),
    "narrow": (
        "The result is too large. Request a bounded subset or a smaller view and continue. "
        "Do not ask the owner to paginate."
    ),
    "retry_read": (
        "This safe read failed. Inspect health when relevant and retry the read. "
        "The request was understood."
    ),
    "reconcile": (
        "A financial mutation may have reached the broker. Reconcile the journal. Do not resend."
    ),
    "reload": "Authoritative state changed. Reload the current record before continuing.",
    "wait": (
        "Required external state is unavailable. Wait for recovery or report the evidence as "
        "unavailable. Do not invent prices, candles, or account state."
    ),
    "change_strategy": (
        "This route already failed. Choose a different tool or a narrower query. "
        "Do not repeat the same call."
    ),
    "ask_owner": (
        "Only the owner can supply this decision. Do not ask them to repair an internal schema."
    ),
    "terminal": (
        "This route cannot succeed. Report the execution failure. The request was understood."
    ),
}


def side_effect(
    name: str, read_only: bool
) -> Literal["read_only", "idempotent", "mutating", "irreversible"]:
    if name in FINANCIAL_TOOLS:
        return "irreversible"
    if read_only:
        return "read_only"
    return "mutating"


def activity_for_tool(name: str) -> Activity:
    if name.startswith(("market_", "chart_", "relationship_", "account_")):
        return "gathering"
    if name.startswith(("collaboration_", "subagent_", "child_agent_")):
        return "consulting"
    return "working"


_RUN_ACTIVITY: dict[str, Activity] = {
    "gathering": "gathering",
    "consulting": "consulting",
    "recovering_broker": "recovering_broker",
    "working": "working",
}


def select_activity(
    *,
    paused: bool,
    approvals: int,
    authorizations: int,
    broker_degraded: bool,
    collaborating: bool,
    watching: bool,
    working: bool,
    run_activity: str | None,
) -> Activity:
    if paused:
        return "paused"
    if approvals or authorizations:
        return "waiting_approval"
    if broker_degraded:
        return "recovering_broker"
    if collaborating:
        return "consulting"
    if watching and not working:
        return "waiting_market"
    if run_activity in _RUN_ACTIVITY:
        return _RUN_ACTIVITY[run_activity]
    if working:
        return "working"
    return "working"


def classify(code: str, *, tool: str, read_only: bool) -> tuple[Classification, Recovery, bool]:
    known = _EXACT.get(code)
    if tool in FINANCIAL_TOOLS and (known is None or known[1] == "retry_read"):
        return "ambiguous_mutation", "reconcile", False
    if known:
        return known
    if "timeout" in code or code.endswith("_unavailable"):
        kind: Classification = (
            "connection_failure"
            if "broker" in code or "connection" in code
            else "temporary_unavailable"
        )
        recovery: Recovery = "retry_read" if read_only or tool not in FINANCIAL_TOOLS else "wait"
        return kind, recovery, False
    if "stale" in code:
        return "stale_state", "retry_read" if tool not in FINANCIAL_TOOLS else "wait", False
    if code.endswith("_not_found") or code == "not_found":
        return "not_found", "change_strategy", False
    if "forbidden" in code or code.endswith("_denied"):
        return "permission_denied", "terminal", False
    if tool in FINANCIAL_TOOLS:
        return "ambiguous_mutation", "reconcile", False
    if read_only:
        return "temporary_unavailable", "retry_read", False
    return "terminal_domain_failure", "change_strategy", False


def guidance(recovery: Recovery) -> str:
    return _GUIDANCE[recovery]


def argument_key(tool: str, arguments: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def record_failure(
    routes: list[Any], *, key: str, tool: str, code: str, classification: str
) -> tuple[list[dict[str, Any]], int]:
    updated = [dict(cast(dict[str, Any], route)) for route in routes if isinstance(route, dict)]
    matched = next(
        (route for route in updated if route.get("key") == key and route.get("code") == code),
        None,
    )
    if matched is None:
        matched = {
            "key": key,
            "tool": tool,
            "code": code,
            "classification": classification,
            "count": 0,
        }
        updated.append(matched)
    matched["count"] = int(matched.get("count", 0)) + 1
    matched["classification"] = classification
    if len(updated) > ROUTE_LIMIT:
        updated = sorted(updated, key=lambda route: int(route.get("count", 0)))[-ROUTE_LIMIT:]
    return updated, int(matched["count"])


def route_repeated(routes: list[Any], key: str) -> bool:
    return any(
        isinstance(route, dict)
        and cast(dict[str, Any], route).get("key") == key
        and int(cast(dict[str, Any], route).get("count", 0)) >= REPEAT_LIMIT
        for route in routes
    )


def financial_resend_blocked(routes: list[Any], tool: str) -> bool:
    if tool not in FINANCIAL_TOOLS:
        return False
    return any(
        isinstance(route, dict)
        and cast(dict[str, Any], route).get("tool") in FINANCIAL_TOOLS
        and cast(dict[str, Any], route).get("classification") == "ambiguous_mutation"
        for route in routes
    )


def public_routes(routes: list[Any]) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for route in routes:
        if not isinstance(route, dict):
            continue
        item = cast(dict[str, Any], route)
        tool = str(item.get("tool", ""))[:80]
        code = str(item.get("code", ""))[:80]
        if not tool or not code:
            continue
        visible.append(
            {
                "tool": tool,
                "code": code,
                "classification": str(item.get("classification", ""))[:80],
                "count": int(item.get("count", 0)),
            }
        )
    return visible[-ROUTE_LIMIT:]


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in cast(list[Any], value) if isinstance(item, str)]


def schema_fields(schema: dict[str, Any]) -> list[dict[str, Any]]:
    properties_raw = schema.get("properties")
    if not isinstance(properties_raw, dict):
        return []
    properties = cast(dict[str, Any], properties_raw)
    required_names = set(_strings(schema.get("required")))
    names = [name for name in properties if name in required_names]
    names.extend(name for name in properties if name not in required_names)
    fields: list[dict[str, Any]] = []
    for name in names[:24]:
        raw = properties.get(name)
        spec = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
        type_name = spec.get("type")
        field: dict[str, Any] = {
            "name": name[:64],
            "type": type_name[:32] if isinstance(type_name, str) else "object",
            "required": name in required_names,
        }
        enum_raw = spec.get("enum")
        values = _strings(enum_raw)
        if (
            isinstance(enum_raw, list)
            and len(values) == len(cast(list[Any], enum_raw))
            and len(values) <= 8
        ):
            field["enum"] = [item[:40] for item in values]
        fields.append(field)
    return fields


def bounded_keys(result: dict[str, Any]) -> list[str]:
    return [key[:40] for key in result if key.isidentifier()][:24]


def observation(
    *,
    code: str,
    tool: str,
    read_only: bool,
    recovery_override: Recovery | None = None,
    issues: list[dict[str, Any]] | None = None,
    fields: list[dict[str, Any]] | None = None,
    result_fields: list[str] | None = None,
    route_repeated_now: bool = False,
) -> dict[str, Any]:
    classification, recovery, owner_required = classify(code, tool=tool, read_only=read_only)
    if recovery_override:
        recovery = recovery_override
        owner_required = recovery == "ask_owner"
    if route_repeated_now and recovery not in {"reconcile", "ask_owner", "terminal"}:
        recovery = "change_strategy"
    payload: dict[str, Any] = {
        "ok": False,
        "code": code,
        "classification": classification,
        "recovery": recovery,
        "owner_required": owner_required,
        "request_understood": True,
        "guidance": guidance(recovery),
        "side_effect": side_effect(tool, read_only),
        "retryable": recovery in {"repair", "narrow", "retry_read", "reload"}
        and not route_repeated_now,
    }
    if issues:
        payload["issues"] = issues[:12]
    if fields:
        payload["schema_fields"] = fields[:24]
    if result_fields:
        payload["result_fields"] = result_fields[:24]
    if route_repeated_now:
        payload["route_repeated"] = True
    return payload
