from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from lonora_contracts.opportunity import ThesisDefinition
from lonora_contracts.trading import TradeRequest
from lonora_session.idempotency import request_hash
from lonora_trading.idempotency import trade_fingerprint
from pydantic import ValidationError


def test_optional_thesis_preserves_legacy_financial_operation_fingerprint():
    request = TradeRequest(
        account_id="owner-account",
        operation_id="existing-operation",
        symbol="EURUSDm",
        action="buy",
        volume=Decimal("0.1"),
    )
    old = request.model_dump(
        mode="json", exclude={"thesis_id", "clear_stop_loss", "clear_take_profit"}
    )
    assert trade_fingerprint(request) == request_hash(old)
    assert trade_fingerprint(
        request.model_copy(update={"thesis_id": "real-thesis-id"})
    ) != trade_fingerprint(request)


def test_thesis_expiry_and_decay_are_explicit_timezone_aware_strategy_horizons():
    now = datetime.now(UTC)
    values = dict(
        direction="BUY",
        rationale="Observed evidence",
        entry_condition="Confirmed watch",
        invalidation_condition="Invalidated watch",
        strategy_version="fixture-v1",
        expires_at=now + timedelta(hours=1),
    )
    assert ThesisDefinition.model_validate(values).decay_at is None
    assert ThesisDefinition.model_validate(
        {**values, "decay_at": now + timedelta(minutes=30)}
    ).decay_at
    with pytest.raises(ValidationError):
        ThesisDefinition.model_validate({**values, "decay_at": now + timedelta(hours=2)})
    with pytest.raises(ValidationError):
        ThesisDefinition.model_validate({**values, "expires_at": now.replace(tzinfo=None)})
