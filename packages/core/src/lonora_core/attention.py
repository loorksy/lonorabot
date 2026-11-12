"""Structured event classification; never match human text or invent a market signal."""

from typing import Any

from lonora_contracts.attention import AttentionClassification, AttentionCode

ATTENTION_KINDS = frozenset(
    {
        "trading.approval.updated",
        # Owner action cards follow these (lonora_gateway.owner_cards); an operation that
        # becomes ambiguous is also the owner's "operation_uncertain" item.
        "trading.operation_updated",
        "broker.external_activity",
        "watch.confirmed",
        "watch.forming",
        "watch.invalidated",
        "watch.suspended_health",
        "watch.resumed_health",
        "watch.expired",
        "opportunity.transition",
        "collaboration.updated",
        "collaboration.completed",
        "task.failed",
        "task.attention_required",
        "task.degraded",
        "task.retry_scheduled",
        "task.updated",
        # A background wake that failed: the item its source stood down for (11.5) returns.
        "run.failed",
        # Cards that wait for the owner (the Secret card) and their end.
        "owner_action.updated",
    }
)
# Owner-action card kinds whose pending card is an attention item, by code.
CARD_ATTENTION: dict[str, AttentionCode] = {"connect_credential": "secret_requested"}


def classify_attention(kind: str, payload: dict[str, Any]) -> AttentionClassification:
    resource = str(
        payload.get("id") or payload.get("watch_id") or payload.get("account_id") or "system"
    )
    transition = str(
        payload.get("version")
        or payload.get("transition_id")
        or payload.get("attempt")
        or payload.get("status")
        or payload.get("state")
        or kind
    )
    if kind == "trading.operation_updated":
        resource = str(payload.get("operation_id") or resource)
    if kind in {"watch.suspended_health", "watch.resumed_health"}:
        transition = str(payload.get("health", {}).get("observed_at") or transition)
    result = AttentionClassification(
        importance="silent", code="internal_update", resource_id=resource, transition=transition
    )
    if kind == "trading.operation_updated" and payload.get("status") == "ambiguous":
        # One item per operation: later ambiguous rewrites of the row are the same fact.
        result.importance, result.code = "action_required", "operation_uncertain"
        transition = "ambiguous"
    elif kind == "trading.approval.updated":
        result.importance, result.code = (
            ("action_required", "approval_required")
            if payload.get("status") == "pending"
            else ("informational", "approval_resolved")
        )
    elif kind == "owner_action.updated":
        code = CARD_ATTENTION.get(str(payload.get("kind")))
        if code is not None and payload.get("status") == "pending":
            result.importance, result.code = "action_required", code
    elif kind == "broker.external_activity":
        transition = str(payload.get("id") or transition)
        # VISION 11.5: the agent this change woke reports it or stays silent; no item
        # stands in beside its reply.
        if payload.get("wakes_agent") is not True:
            result.importance, result.code = "important_change", "external_broker_activity"
    elif kind == "watch.confirmed" and payload.get("wakes_agent") is not True:
        # A confirmation that woke nobody (its cooldown) stays the owner's item.
        result.importance, result.code = "opportunity", "setup_confirmed"
    elif kind in {"watch.invalidated", "watch.expired"}:
        result.importance, result.code = "important_change", "thesis_invalidated"
    elif kind == "opportunity.transition" and payload.get("wakes_agent") is not True:
        if payload.get("status") == "confirmed":
            result.importance, result.code = "opportunity", "setup_confirmed"
        elif payload.get("status") in {"invalidated", "degraded", "expired"}:
            result.importance, result.code = "important_change", "thesis_invalidated"
    elif kind == "collaboration.completed" and payload.get("result_empty") is not True:
        result.importance, result.code = "important_change", "collaboration_completed"
    elif kind == "task.failed":
        result.importance, result.code = (
            "action_required"
            if payload.get("recovery") in {"owner", "modify_plan"}
            else "important_change",
            "task_review",
        )
    elif kind == "task.attention_required":
        # Unfinished work waits for the owner's direction instead of failing.
        result.importance, result.code = "action_required", "task_review"
    elif kind == "task.degraded":
        # Monitoring keeps retrying through an outage; nothing waits on the owner.
        result.importance, result.code = "important_change", "task_degraded"
    elif (
        kind == "task.updated"
        and payload.get("status") == "completed"
        and payload.get("result_empty") is not True
    ):
        result.importance, result.code = "informational", "task_completed"
    result.transition = transition
    return result
