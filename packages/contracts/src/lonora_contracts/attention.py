"""Attention is a projection of runtime truth, not another chat timeline."""

from typing import Literal

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
    "task_completed",
    "internal_update",
    "super_bot_authorization",
    "super_bot_changed",
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
