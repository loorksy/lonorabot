"""Read-only postconditions, with deliberately inconsistent acknowledgment fixtures."""

from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.broker import BrokerStateReader
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_trading.verification import verify_effect


def snapshot() -> ExecutionSnapshot:
    return ExecutionSnapshot(
        account=AccountState(
            id="fixture",
            currency="USD",
            balance=Decimal(1000),
            equity=Decimal(1000),
            margin=Decimal(0),
            free_margin=Decimal(1000),
            observed_at=utcnow(),
        ),
        positions=[
            Position(
                id="manual",
                symbol="PAIR.sfx",
                side="buy",
                volume=Decimal("1"),
                open_price=Decimal(100),
                stop_loss=Decimal(90),
                take_profit=Decimal(110),
            )
        ],
        orders=[
            Order(
                id="pending",
                symbol="PAIR.sfx",
                side="buy_limit",
                volume=Decimal("0.2"),
                price=Decimal(99),
                stop_loss=Decimal(90),
            )
        ],
        observed_at=utcnow(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        "buy",
        "sell",
        "buy_limit",
        "sell_limit",
        "buy_stop",
        "sell_stop",
        "close_position",
        "modify_position",
        "cancel_order",
        "modify_order",
    ],
)
async def test_each_mutation_requires_independent_matching_broker_state(action: str):
    before = snapshot()
    args: dict[str, object] = {"account_id": "fixture", "symbol": "PAIR.sfx", "action": action}
    positions, orders = list(before.positions), list(before.orders)
    broker_id = "new"
    if action in {"buy", "sell"}:
        args["volume"] = "0.2"
        positions.append(
            Position(
                id=broker_id,
                symbol="PAIR.sfx",
                side=action,
                volume=Decimal("0.2"),
                open_price=Decimal(100),
            )
        )
    elif action in {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}:
        args.update(volume="0.2", price="99")
        orders.append(
            Order(
                id=broker_id,
                symbol="PAIR.sfx",
                side=action,
                volume=Decimal("0.2"),
                price=Decimal(99),
            )
        )
    elif action == "close_position":
        args.update(position_id="manual", volume="0.2")
        positions = [before.positions[0].model_copy(update={"volume": Decimal("0.8")})]
    elif action == "modify_position":
        args.update(position_id="manual", stop_loss="91")
        positions = [before.positions[0].model_copy(update={"stop_loss": Decimal(91)})]
    elif action == "cancel_order":
        args["order_id"] = "pending"
        orders = []
    else:
        args.update(order_id="pending", price="98", clear_stop_loss=True)
        orders = [before.orders[0].model_copy(update={"price": Decimal(98), "stop_loss": None})]
    request = TradeRequest.model_validate(args)
    receipt = TradeResult(
        operation_id=request.operation_id, status="confirmed", broker_id=broker_id
    )
    broker = SimpleNamespace(
        positions=AsyncMock(return_value=positions), orders=AsyncMock(return_value=orders)
    )
    verified = await verify_effect(cast(BrokerStateReader, broker), request, receipt, before)
    assert verified["status"] == "verified" and verified["financial_retry_allowed"] is False
    assert broker.positions.await_count == broker.orders.await_count == 1
    broker.positions.return_value, broker.orders.return_value = before.positions, before.orders
    inconsistent = await verify_effect(cast(BrokerStateReader, broker), request, receipt, before)
    assert inconsistent["status"] == "pending"  # ack alone cannot pass


@pytest.mark.asyncio
async def test_verification_failure_never_resubmits_and_missing_protection_is_not_verified():
    before = snapshot()
    request = TradeRequest(
        account_id="fixture",
        symbol="PAIR.sfx",
        action="buy",
        volume=Decimal("0.2"),
        stop_loss=Decimal(90),
    )
    receipt = TradeResult(operation_id=request.operation_id, status="confirmed", broker_id="new")
    broker = SimpleNamespace(positions=AsyncMock(side_effect=TimeoutError()), orders=AsyncMock())
    result = await verify_effect(cast(BrokerStateReader, broker), request, receipt, before)
    assert result["status"] == "pending" and result["financial_retry_allowed"] is False
    broker.positions.side_effect = None
    broker.positions.return_value = [
        Position(
            id="new", symbol="PAIR.sfx", side="buy", volume=Decimal("0.2"), open_price=Decimal(100)
        )
    ]
    broker.orders.return_value = []
    assert (await verify_effect(cast(BrokerStateReader, broker), request, receipt, before))[
        "status"
    ] == "pending"
