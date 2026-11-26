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
    "broker_rate_limited",
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
    "gateway_stopped",
    "model_access_failed",
]
AttentionStatus = Literal["pending", "ready", "seen", "suppressed"]
# Why a model provider refused background work (``model_access_failed``): a rejected key,
# spent credit, a model the key may not use, or one the provider does not have.
ModelAccessReason = Literal["auth", "billing", "permission", "model_not_found"]

# The events of mandate 11.4 (six kinds since Amendment 5) that need the owner, by code:
# each is one item, ready at once and withdrawn when its card ends or its problem clears.
AttentionEvent = Literal[
    "trade_approval",
    "settle_operation",
    "secret_request",
    "mandate_card",
    "broker_health",
    "background_health",
]
ATTENTION_EVENTS: dict[AttentionCode, AttentionEvent] = {
    "approval_required": "trade_approval",
    "operation_uncertain": "settle_operation",
    "secret_requested": "secret_request",
    "mandate_proposed": "mandate_card",
    "broker_token_rejected": "broker_health",
    "broker_account_undeployed": "broker_health",
    "broker_connection_lost": "broker_health",
    "broker_rate_limited": "broker_health",
    # Lonora's own background work stopped (Amendment 5): no Gateway is running, or a model
    # provider refused access to background work (one item per route and cause).
    "gateway_stopped": "background_health",
    "model_access_failed": "background_health",
}
# The broker health problems of mandate 9.4, one item per account and problem.
BROKER_HEALTH_CODES: tuple[AttentionCode, ...] = (
    "broker_token_rejected",
    "broker_account_undeployed",
    "broker_connection_lost",
    "broker_rate_limited",
)


# What the "needs your attention" view (11.7) lists: the owner's events, the questions
# a run waits on the owner to answer, the Tasks that need the owner's review, and an
# agent's own unread alert (owner_notify), and the watchdog's unread items about an
# unresolved operation or quarantined work; neither has another place outside chat.
AttentionViewKind = Literal[
    "trade_approval",
    "settle_operation",
    "secret_request",
    "mandate_card",
    "broker_health",
    "background_health",
    "owner_question",
    "task_review",
    "agent_alert",
    "system_alert",
]


class AttentionViewRow(Contract):
    """One row of the attention view, projected by the server; the only model text in
    it is an agent alert's own summary.

    The row opens its conversation (``thread_id``, or the group's), where the fixed card
    or the question stands; opening it decides nothing.
    """

    kind: AttentionViewKind
    id: str
    agent_id: str
    thread_id: str
    group_id: str | None = None
    # The attention item's code (None for a question a run waits on).
    code: AttentionCode | None = None
    run_id: str | None = None
    symbol: str | None = None
    # An agent's alert: its plain summary for the owner (the agent's words).
    summary: str | None = None
    # A refused model (model_access_failed): the failure family and the provider's fixed
    # name (None for an OpenAI-compatible endpoint), never the provider's message.
    reason: ModelAccessReason | None = None
    provider_name: str | None = None
    # The owner has already looked at it: the item was opened, or the question's
    # conversation was read up to it. Such a row stays listed but lights no dot.
    seen: bool = False
    created_at: datetime


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
