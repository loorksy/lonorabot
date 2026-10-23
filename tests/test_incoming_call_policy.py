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
