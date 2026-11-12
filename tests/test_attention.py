"""Attention classification consumes structured runtime transitions only."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from lonora_bus.attention import attention_text
from lonora_contracts.attention import (
    ATTENTION_EVENTS,
    BROKER_HEALTH_CODES,
    AttentionPolicy,
)
from lonora_core.attention import ATTENTION_KINDS, classify_attention
from lonora_core.broker_health import LOST_CONNECTION_GRACE, broker_problem
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
        (
            "task.attention_required",
            {"id": "task", "version": 4, "reason": "task_steps_incomplete"},
            "action_required",
            "task_review",
        ),
        (
            "task.degraded",
            {"id": "task", "reason": "model_unavailable", "transition_id": "2026-11-07T12:00"},
            "important_change",
            "task_degraded",
        ),
        (
            "task.updated",
            {"status": "waiting", "waiting_reason": "owner_attention"},
            "silent",
            "internal_update",
        ),
        ("task.updated", {"status": "completed"}, "informational", "task_completed"),
        # Broker transitions raise no item of their own; health is read from stored state.
        ("broker.recovered", {"previous_status": "degraded"}, "silent", "internal_update"),
        ("broker.degraded", {"status": "disconnected"}, "silent", "internal_update"),
        (
            "owner_action.updated",
            {"id": "card", "kind": "connect_credential", "status": "pending"},
            "action_required",
            "secret_requested",
        ),
        (
            "owner_action.updated",
            {"id": "card", "kind": "connect_credential", "status": "cancelled"},
            "silent",
            "internal_update",
        ),
        (
            "owner_action.updated",
            {"id": "card", "kind": "trust_source", "status": "pending"},
            "silent",
            "internal_update",
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
    for code in ("emergency_stop", "task_review", *ATTENTION_EVENTS):
        assert attention_text(code, "ar") != attention_text(code, "en")
        assert attention_text(code, "ar") != attention_text("unknown", "ar")


NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


def recovery(status: str, reason: str, age: timedelta) -> dict[str, Any]:
    return {"status": status, "reason_code": reason, "since": (NOW - age).isoformat()}


@pytest.mark.parametrize(
    ("status", "reason", "age", "problem"),
    [
        ("disconnected", "broker_credentials_rejected", timedelta(), "broker_token_rejected"),
        ("disconnected", "broker_account_undeployed", timedelta(), "broker_account_undeployed"),
        ("disconnected", "broker_account_not_found", timedelta(), "broker_account_undeployed"),
        ("disconnected", "broker_connection_timeout", timedelta(seconds=119), None),
        (
            "disconnected",
            "broker_connection_timeout",
            LOST_CONNECTION_GRACE,
            "broker_connection_lost",
        ),
        (
            "disconnected",
            "broker_recovery_unavailable",
            timedelta(hours=1),
            "broker_connection_lost",
        ),
        # A connected account with unresolved operations is reconciling, not a problem.
        ("degraded", "broker_reconciliation_pending", timedelta(hours=1), None),
        ("connected", "broker_reconciled", timedelta(hours=1), None),
    ],
)
def test_broker_problem(status: str, reason: str, age: timedelta, problem: str | None) -> None:
    found = broker_problem(recovery(status, reason, age), NOW)
    assert (found[0] if found else None) == problem
    if found:
        # The episode is named by when the account became disconnected.
        assert found[1] == (NOW - age).isoformat()


def test_broker_problem_without_state() -> None:
    assert broker_problem({}, NOW) is None


def test_the_owner_events_have_one_code_set() -> None:
    assert set(BROKER_HEALTH_CODES) <= set(ATTENTION_EVENTS)
    assert set(ATTENTION_EVENTS.values()) == {
        "trade_approval",
        "settle_operation",
        "secret_request",
        "broker_health",
    }
    assert "owner_action.updated" in ATTENTION_KINDS
    assert not {"broker.degraded", "broker.recovered"} & ATTENTION_KINDS
