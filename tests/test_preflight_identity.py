"""Preflight must preserve the broker's actual internal account identity."""

from decimal import Decimal
from typing import Literal
from unittest.mock import AsyncMock, Mock

import pytest
from lonora_adapter_kit.broker import BrokerStateReader
from lonora_contracts.account import AccountState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Instrument, Quote
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_trading.preflight import preflight


def broker_fixture(account_id: str = "selected-connection") -> tuple[Mock, AccountState]:
    account = AccountState(
        id=account_id,
        currency="USDc",
        balance=Decimal("100000"),
        equity=Decimal("100000"),
        margin=Decimal(0),
        free_margin=Decimal("100000"),
        observed_at=utcnow(),
    )
    instrument = Instrument(
        symbol="exact.symbol#",
        digits=2,
        tick_size=Decimal("0.01"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("100"),
        volume_step=Decimal("0.01"),
    )
    quote = Quote(
        symbol=instrument.symbol,
        bid=Decimal("100"),
        ask=Decimal("100.02"),
        observed_at=utcnow(),
        source="scripted-preflight-identity-fixture",
    )
    broker = Mock(spec=BrokerStateReader)
    broker.instrument = AsyncMock(return_value=instrument)
    broker.account = AsyncMock(return_value=account)
    broker.positions = AsyncMock(return_value=[])
    broker.orders = AsyncMock(return_value=[])
    broker.quote = AsyncMock(return_value=quote)
    broker.execute = AsyncMock()
    return broker, account


def request(
    action: Literal["buy", "sell", "cancel_order", "close_position"] = "buy",
) -> TradeRequest:
    return TradeRequest(
        account_id="selected-connection",
        symbol="exact.symbol#",
        action=action,
        volume=Decimal("0.10") if action in {"buy", "sell"} else None,
        order_id="manual-order" if action == "cancel_order" else None,
        position_id="manual-position" if action == "close_position" else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("financial_authority", [False, True])
@pytest.mark.parametrize("action", ["buy", "sell", "cancel_order", "close_position"])
async def test_account_mismatch_fails_before_target_reads_and_preserves_actual_identity(
    financial_authority: bool,
    action: Literal["buy", "sell", "cancel_order", "close_position"],
) -> None:
    broker, account = broker_fixture("another-connection")
    account.trade_allowed = False
    with pytest.raises(LonoraError) as caught:
        await preflight(broker, request(action), financial_authority=financial_authority)
    assert caught.value.code == "broker_account_mismatch" and caught.value.status == 409
    assert account.id == "another-connection"
    broker.account.assert_awaited_once()
    broker.positions.assert_not_awaited()
    broker.orders.assert_not_awaited()
    broker.quote.assert_not_awaited()
    broker.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("financial_authority", [False, True])
@pytest.mark.parametrize("action", ["buy", "sell"])
async def test_matching_identity_passes_through_without_rewriting_broker_state(
    financial_authority: bool, action: Literal["buy", "sell"]
) -> None:
    broker, account = broker_fixture()
    snapshot = await preflight(broker, request(action), financial_authority=financial_authority)
    assert snapshot.account is account and snapshot.account.id == "selected-connection"
    assert snapshot.account.currency == "USDc"
    assert snapshot.quote is not None and snapshot.quote.symbol == "exact.symbol#"
    broker.positions.assert_awaited_once()
    broker.orders.assert_awaited_once()
    broker.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["instrument", "quote"])
async def test_exact_symbol_validation_still_applies(resource: str) -> None:
    broker, _ = broker_fixture()
    reader = broker.instrument if resource == "instrument" else broker.quote
    reader.return_value = reader.return_value.model_copy(update={"symbol": "another.symbol#"})
    with pytest.raises(LonoraError, match="broker_symbol_mismatch"):
        await preflight(broker, request())
    broker.execute.assert_not_awaited()
    if resource == "instrument":
        broker.account.assert_not_awaited()


@pytest.mark.asyncio
async def test_observation_can_inspect_matching_non_tradable_account_without_authorizing() -> None:
    broker, account = broker_fixture()
    account.trade_allowed = False
    with pytest.raises(LonoraError, match="broker_trading_not_allowed"):
        await preflight(broker, request())
    broker.positions.assert_not_awaited()
    snapshot = await preflight(broker, request(), financial_authority=False)
    assert snapshot.account is account and snapshot.account.trade_allowed is False
    broker.execute.assert_not_awaited()
