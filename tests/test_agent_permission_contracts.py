"""Drafts are editable data; only the existing signed envelope grants authority."""

import pytest
from lonora_contracts.account_authority import AccountAuthorityProposal
from lonora_contracts.agent_permissions import (
    CustomizationLimits,
    PermissionChange,
    PermissionCustomization,
    PermissionCustomizationChange,
    PermissionRecord,
)
from pydantic import ValidationError


def test_permission_selection_cannot_grant_unsigned_autonomy():
    for level in ("analysis", "supervised"):
        assert (
            PermissionChange.model_validate({"level": level, "expected_revision": 4}).level == level
        )
    with pytest.raises(ValidationError):
        PermissionChange.model_validate({"level": "autonomous", "expected_revision": 4})
    with pytest.raises(ValidationError):
        PermissionChange.model_validate({"level": "supervised"})
    with pytest.raises(ValidationError):
        PermissionChange.model_validate({"level": "supervised", "expected_revision": -1})
    assert PermissionRecord(owner_id="owner", agent_id="new-agent").fallback_level == "analysis"


def test_partial_customization_round_trips_without_becoming_executable():
    partial = PermissionCustomization(
        account_id="",
        actions=[],
        limits=CustomizationLimits(maximum_order_volume="0.", maximum_actions="editing"),
    )
    stored = PermissionRecord(owner_id="owner", agent_id="agent", customization=partial)
    restored = PermissionRecord.model_validate(stored.model_dump(mode="json"))
    assert restored == stored and restored.fallback_level == "analysis"
    assert restored.customization is not None
    assert restored.customization.limits.maximum_order_volume == "0."
    with pytest.raises(ValidationError):
        AccountAuthorityProposal.model_validate(
            {
                "thread_id": "thread",
                "account_id": partial.account_id,
                "management_mode": "full",
                "actions": partial.actions,
                "symbol_scope": partial.symbol_scope,
                "symbols": partial.symbols,
                **partial.limits.model_dump(),
            }
        )


def test_non_executable_drafts_still_reject_unbounded_or_unknown_data():
    with pytest.raises(ValidationError):
        PermissionCustomization.model_validate({"limits": {"maximum_actions": "1" * 81}})
    with pytest.raises(ValidationError):
        PermissionCustomization.model_validate({"actions": ["transfer_funds"]})
    with pytest.raises(ValidationError):
        PermissionCustomization.model_validate({"grant_active": True})
    with pytest.raises(ValidationError):
        PermissionCustomizationChange.model_validate(
            {
                "customization": PermissionCustomization().model_dump(mode="json"),
            }
        )
