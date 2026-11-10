from datetime import UTC, datetime

import pytest
from lonora_contracts.incoming_calls import IncomingCallPolicy
from pydantic import ValidationError


def test_default_is_disabled_and_financially_unrelated():
    policy = IncomingCallPolicy()
    assert not policy.enabled and not policy.opportunities and not policy.action_required
    assert "trading" not in IncomingCallPolicy.model_fields


def test_consent_requires_device_and_valid_timezone():
    with pytest.raises(ValidationError):
        IncomingCallPolicy(enabled=True)
    with pytest.raises(ValidationError):
        IncomingCallPolicy(timezone="Made/Up")
    # A zone directory, not a zone: refused as invalid, never a server error.
    with pytest.raises(ValidationError, match="invalid_timezone"):
        IncomingCallPolicy(timezone="America")
    with pytest.raises(ValidationError):
        IncomingCallPolicy(quiet_start_hour=22)


def test_quiet_hours_handle_overnight_and_local_timezone():
    policy = IncomingCallPolicy(timezone="Asia/Dubai", quiet_start_hour=22, quiet_end_hour=7)
    assert policy.quiet(datetime(2026, 10, 21, 19, tzinfo=UTC))
    assert policy.quiet(datetime(2026, 10, 21, 1, tzinfo=UTC))
    assert not policy.quiet(datetime(2026, 10, 21, 10, tzinfo=UTC))
    assert IncomingCallPolicy(quiet_start_hour=8, quiet_end_hour=17).quiet(
        datetime(2026, 10, 21, 12, tzinfo=UTC)
    )


def test_quiet_hours_to_the_minute():
    """Owner decision Q47: quiet hours are kept in minutes (22:30 → 07:15)."""
    policy = IncomingCallPolicy(quiet_start_minute=22 * 60 + 30, quiet_end_minute=7 * 60 + 15)
    assert (policy.quiet_start_hour, policy.quiet_end_hour) == (22, 7)
    assert not policy.quiet(datetime(2026, 10, 21, 22, 29, tzinfo=UTC))
    assert policy.quiet(datetime(2026, 10, 21, 22, 30, tzinfo=UTC))
    assert policy.quiet(datetime(2026, 10, 22, 7, 14, tzinfo=UTC))
    assert not policy.quiet(datetime(2026, 10, 22, 7, 15, tzinfo=UTC))
    until = policy.quiet_until(datetime(2026, 10, 22, 3, 0, tzinfo=UTC))
    assert until == datetime(2026, 10, 22, 7, 15, tzinfo=UTC)


def test_hour_only_clients_keep_working():
    """A client that only knows whole hours (mobile, the memory tool) sets minutes on the hour;
    a stored minute that disagrees with a newly sent hour yields to the hour."""
    legacy = IncomingCallPolicy(quiet_start_hour=22, quiet_end_hour=6)
    assert (legacy.quiet_start_minute, legacy.quiet_end_minute) == (1320, 360)
    edited = IncomingCallPolicy(
        quiet_start_hour=23, quiet_end_hour=6, quiet_start_minute=1350, quiet_end_minute=375
    )
    assert (edited.quiet_start_minute, edited.quiet_end_minute) == (1380, 375)
    cleared = IncomingCallPolicy(quiet_start_hour=None, quiet_end_hour=None)
    assert cleared.quiet_start_minute is None and cleared.quiet_end_minute is None
    with pytest.raises(ValidationError):
        IncomingCallPolicy(quiet_start_minute=1440, quiet_end_minute=0)
    with pytest.raises(ValidationError):
        IncomingCallPolicy(quiet_start_minute=60)
    # Clearing one side of a stored window is incomplete, never a silent keep.
    with pytest.raises(ValidationError):
        IncomingCallPolicy(
            quiet_start_hour=None, quiet_end_hour=6, quiet_start_minute=1350, quiet_end_minute=375
        )
    # An empty window (start = end) would silence everything all day: refused.
    with pytest.raises(ValidationError, match="incoming_call_quiet_hours_empty"):
        IncomingCallPolicy(quiet_start_minute=600, quiet_end_minute=600)
