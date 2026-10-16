"""Structured event classification; never match human text or invent a market signal."""

from typing import Any

from lonora_contracts.attention import AttentionClassification

ATTENTION_KINDS = frozenset(
    {
        "trading.controls_updated",
        "trading.approval.updated",
        "broker.degraded",
        "broker.recovered",
        "broker.external_activity",
        "watch.confirmed",
        "watch.forming",
        "watch.invalidated",
        "watch.suspended_health",
        "watch.resumed_health",
        "watch.expired",
        "opportunity.transition",
        "goals.updated",
        "collaboration.updated",
        "collaboration.completed",
        "task.failed",
        "task.retry_scheduled",
        "task.updated",
    }
)


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
    if kind in {"watch.suspended_health", "watch.resumed_health"}:
        transition = str(payload.get("health", {}).get("observed_at") or transition)
    result = AttentionClassification(
        importance="silent", code="internal_update", resource_id=resource, transition=transition
    )
    if kind == "trading.controls_updated" and payload.get("emergency_stop") is True:
        result.importance, result.code = "critical", "emergency_stop"
    elif kind == "trading.approval.updated":
        result.importance, result.code = (
            ("action_required", "approval_required")
            if payload.get("status") == "pending"
            else ("informational", "approval_resolved")
        )
    elif kind in {"broker.degraded", "broker.recovered"}:
        result.importance, result.code = (
            "important_change",
            "broker_degraded" if kind.endswith("degraded") else "broker_recovered",
        )
        if kind.endswith("recovered") and not payload.get("previous_status"):
            result.importance = "silent"
    elif kind == "broker.external_activity":
        result.importance, result.code = "important_change", "external_broker_activity"
        transition = str(payload.get("id") or transition)
    elif kind == "watch.confirmed":
        result.importance, result.code = "opportunity", "setup_confirmed"
    elif kind in {"watch.invalidated", "watch.expired"}:
        result.importance, result.code = "important_change", "thesis_invalidated"
    elif kind == "opportunity.transition":
        if payload.get("status") == "confirmed":
            result.importance, result.code = "opportunity", "setup_confirmed"
        elif payload.get("status") in {"invalidated", "degraded", "expired"}:
            result.importance, result.code = "important_change", "thesis_invalidated"
    elif kind == "goals.updated" and payload.get("status") in {
        "paused",
        "blocked",
        "completed",
        "cancelled",
    }:
        result.importance, result.code = "important_change", "goal_changed"
    elif kind == "collaboration.completed":
        result.importance, result.code = "important_change", "collaboration_completed"
    elif kind == "task.failed":
        result.importance, result.code = (
            "action_required"
            if payload.get("recovery") in {"owner", "modify_plan"}
            else "important_change",
            "task_review",
        )
    elif kind == "task.updated" and payload.get("status") == "completed":
        result.importance, result.code = "informational", "task_completed"
    result.transition = transition
    return result
