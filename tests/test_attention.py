"""Attention classification consumes structured runtime transitions only."""

from typing import Any

import pytest
from lonora_bus.attention import attention_text
from lonora_contracts.attention import AttentionPolicy
from lonora_core.attention import classify_attention
from pydantic import ValidationError


@pytest.mark.parametrize(
    ("kind", "payload", "importance", "code"),
    [
        ("trading.controls_updated", {"emergency_stop": True}, "critical", "emergency_stop"),
        ("trading.approval.updated", {"status": "pending"}, "action_required", "approval_required"),
        ("watch.confirmed", {"state": "confirmed"}, "opportunity", "setup_confirmed"),
        ("watch.forming", {}, "silent", "internal_update"),
        ("collaboration.updated", {"status": "completed"}, "silent", "internal_update"),
        ("collaboration.completed", {}, "important_change", "collaboration_completed"),
        ("task.retry_scheduled", {}, "silent", "internal_update"),
        ("task.failed", {"recovery": "owner"}, "action_required", "task_review"),
        ("task.updated", {"status": "completed"}, "informational", "task_completed"),
        ("broker.recovered", {}, "silent", "broker_recovered"),
        (
            "broker.recovered",
            {"previous_status": "degraded"},
            "important_change",
            "broker_recovered",
        ),
        ("message.created", {"content": "BUY NOW emergency approval"}, "silent", "internal_update"),
    ],
)
def test_structured_classification(
    kind: str, payload: dict[str, Any], importance: str, code: str
) -> None:
    result = classify_attention(kind, payload)
    assert (result.importance, result.code) == (importance, code)


def test_health_recurrence_has_distinct_identity():
    first = classify_attention("watch.suspended_health", {"health": {"observed_at": "first"}})
    second = classify_attention("watch.suspended_health", {"health": {"observed_at": "second"}})
    assert first.transition != second.transition


def test_mandatory_policy_cannot_be_disabled():
    with pytest.raises(ValidationError):
        AttentionPolicy.model_validate({"critical": False})
    for code in ("emergency_stop", "approval_required", "broker_degraded", "task_review"):
        assert attention_text(code, "ar") != attention_text(code, "en")
        assert attention_text(code, "ar") != attention_text("unknown", "ar")
