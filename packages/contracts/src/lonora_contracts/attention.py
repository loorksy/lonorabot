"""Attention is a projection of runtime truth, not another chat timeline."""

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from .domain import Contract

AttentionImportance = Literal[
    "critical", "action_required", "important_change", "opportunity", "informational", "silent"
]
AttentionCode = Literal[
    "watch_condition_met",
    "approval_required",
    "approval_resolved",
    "broker_token_rejected",
    "broker_account_undeployed",
    "broker_connection_lost",
    "external_broker_activity",
    "setup_confirmed",
    "thesis_invalidated",
    "collaboration_completed",
    "task_review",
    "task_degraded",
    "task_completed",
    "internal_update",
    "super_bot_authorization",
    "super_bot_changed",
    "maintenance_item_quarantined",
    "run_quarantined",
    "operation_unresolved",
    "operation_uncertain",
    "gateway_degraded",
    "agent_notification",
    "secret_requested",
    "mandate_proposed",
]
AttentionStatus = Literal["pending", "ready", "seen", "suppressed"]

# The events of mandate 11.4 that need the owner, by code: each is one item, ready at
# once and withdrawn when its card ends or its problem clears.
AttentionEvent = Literal[
    "trade_approval", "settle_operation", "secret_request", "mandate_card", "broker_health"
]
ATTENTION_EVENTS: dict[AttentionCode, AttentionEvent] = {
    "approval_required": "trade_approval",
    "operation_uncertain": "settle_operation",
    "secret_requested": "secret_request",
    "mandate_proposed": "mandate_card",
    "broker_token_rejected": "broker_health",
    "broker_account_undeployed": "broker_health",
    "broker_connection_lost": "broker_health",
}
# The broker health problems of mandate 9.4, one item per account and problem.
BROKER_HEALTH_CODES: tuple[AttentionCode, ...] = (
    "broker_token_rejected",
    "broker_account_undeployed",
    "broker_connection_lost",
)


class AttentionNotification(Contract):
    """One attention item as the clients and the channels read it.

    It is the payload of the ``attention.updated`` and ``attention.ready`` events.
    """

    id: str
    agent_id: str
    thread_id: str
    importance: AttentionImportance
    code: AttentionCode
    status: AttentionStatus
    parameters: dict[str, Any]
    source_events: list[int]
    source_count: int
    version: int
    created_at: datetime
    updated_at: datetime


class AttentionPolicy(Contract):
    opportunities: bool = True
    informational: bool = False
    locale: Literal["ar", "en"] = "ar"


class AttentionClassification(Contract):
    importance: AttentionImportance
    code: AttentionCode
    resource_id: str
    transition: str


class AttentionSeen(Contract):
    notification_id: str


# What an Agent may raise on its own. An opportunity needs the server's evidence
# revalidation, so an Agent reports one as important_change.
NotifyImportance = Literal["critical", "action_required", "important_change", "informational"]


class OwnerNotifyRequest(Contract):
    importance: NotifyImportance
    summary: str = Field(min_length=8, max_length=400)
    evidence_refs: list[str] = Field(default_factory=list[str], max_length=8)
    dedupe_key: str = Field(min_length=1, max_length=120)
    expires_at: datetime | None = None

    @field_validator("evidence_refs")
    @classmethod
    def bounded_refs(cls, value: list[str]) -> list[str]:
        if any(not 1 <= len(item) <= 200 for item in value):
            raise ValueError("owner_notify_evidence_invalid")
        return value

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("owner_notify_expiry_timezone_required")
        return value
