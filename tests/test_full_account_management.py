"""Versioned explicit account scope: absent legacy limits never grant discretion."""

from datetime import timedelta
from typing import Any

import pytest
from lonora_contracts.account_authority import AccountAuthorityEnvelope, AccountAuthorityProposal
from lonora_contracts.domain import utcnow
from pydantic import ValidationError

LIMITS: dict[str, Any] = {
    "maximum_order_volume": "0.1",
    "maximum_symbol_volume": "0.3",
    "maximum_positions": 3,
    "maximum_pending_orders": 1,
    "maximum_actions": 5,
    "minimum_equity": "8000",
    "valid_until": utcnow() + timedelta(days=1),
}
SCOPE: dict[str, Any] = {
    "thread_id": "conversation",
    "account_id": "account",
    "symbols": ["Exact.symbol#"],
    "actions": ["buy", "modify_position", "close_position"],
}


@pytest.mark.parametrize("missing", list(LIMITS))
@pytest.mark.parametrize("explicit_null", [True, False])
def test_legacy_missing_or_null_limit_never_means_unlimited(missing: str, explicit_null: bool):
    body = {**SCOPE, **LIMITS}
    if explicit_null:
        body[missing] = None
    else:
        body.pop(missing)
    with pytest.raises(ValidationError, match="authority_bounded_limits_required"):
        AccountAuthorityProposal.model_validate(body)


def test_full_management_requires_explicit_mode_and_new_envelope_version():
    full = AccountAuthorityProposal(**SCOPE, management_mode="full")
    assert full.valid_until is None and full.maximum_order_volume is None
    assert full.permits_symbol("Exact.symbol#")
    assert not full.permits_symbol("Exact.symbol")
    with pytest.raises(ValidationError, match="authority_full_management_requires_v2"):
        AccountAuthorityEnvelope(**full.model_dump(), owner_id="owner", agent_id="agent")
    envelope = AccountAuthorityEnvelope(
        **full.model_dump(), owner_id="owner", agent_id="agent", schema_version=2
    )
    assert AccountAuthorityEnvelope.model_validate_json(envelope.model_dump_json()) == envelope


def test_account_scope_is_explicit_and_cannot_be_mixed_with_selected_symbols():
    full = AccountAuthorityProposal.model_validate(
        {**SCOPE, "symbols": [], "management_mode": "full", "symbol_scope": "account"}
    )
    assert full.permits_symbol("any.broker-symbol#")
    for changes in [{"management_mode": "bounded", **LIMITS}, {"symbols": ["EURUSDm"]}]:
        with pytest.raises(ValidationError):
            AccountAuthorityProposal.model_validate({**full.model_dump(), **changes})


@pytest.mark.parametrize("limit", list(LIMITS))
def test_full_management_preserves_explicit_optional_limits(limit: str):
    full = AccountAuthorityProposal(**SCOPE, management_mode="full", **{limit: LIMITS[limit]})
    assert getattr(full, limit) is not None


@pytest.mark.parametrize(
    "values",
    [
        {"maximum_actions": 0},
        {"maximum_order_volume": "NaN"},
        {"maximum_order_volume": "Infinity"},
        {"minimum_equity": "-1"},
        {"valid_until": "2027-01-01T00:00:00"},
        {"maximum_order_volume": "2", "maximum_symbol_volume": "1"},
        {"symbols": []},
        {"actions": ["buy", "buy"]},
    ],
)
def test_full_management_does_not_accept_invalid_or_ambiguous_scope(values: dict[str, Any]):
    with pytest.raises(ValidationError):
        AccountAuthorityProposal.model_validate({**SCOPE, "management_mode": "full", **values})
