"""Attention is a projection of runtime truth, not another chat timeline."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from .domain import Contract

AttentionImportance = Literal[
    "critical", "action_required", "important_change", "opportunity", "informational", "silent"
]
AttentionCode = Literal[
    "watch_condition_met",
    "emergency_stop",
    "approval_required",
    "approval_resolved",
    "broker_degraded",
    "broker_recovered",
    "external_broker_activity",
    "setup_confirmed",
    "thesis_invalidated",
    "goal_changed",
    "collaboration_completed",
    "task_review",
    "task_degraded",
    "task_completed",
    "internal_update",
    "super_bot_authorization",
    "super_bot_changed",
    "agent_notification",
]


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
