"""Exact broker evidence recovery; no network or financial mutations."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_adapters.brokers.metaapi import MetaApiBroker, client_id
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError


def adapter(
    deals: list[dict[str, Any]] | None = None, orders: list[dict[str, Any]] | None = None
) -> tuple[MetaApiBroker, Any]:
    broker = object.__new__(MetaApiBroker)
    broker.evidence = None
    broker.evidence_lock = asyncio.Lock()
    rpc = SimpleNamespace(
        get_positions=AsyncMock(return_value=[]),
        get_orders=AsyncMock(return_value=[]),
        get_deals_by_time_range=AsyncMock(return_value={"deals": deals or []}),
        get_history_orders_by_time_range=AsyncMock(return_value={"historyOrders": orders or []}),
    )

    async def read(method: str, *args: Any) -> Any:
        return await getattr(rpc, method)(*args)

    broker.read_rpc = read
    return broker, rpc


@pytest.mark.asyncio
async def test_old_submission_extends_history_and_broad_cache_serves_younger_operations():
    broker, rpc = adapter(
        orders=[
            {
                "id": "o1",
                "symbol": "US500.cash",
                "clientId": client_id("old"),
                "state": "ORDER_STATE_FILLED",
            }
        ]
    )
    old = datetime.now(UTC) - timedelta(days=40)
    result = await broker.reconcile(
        "old",
        TradeRequest(account_id="a", symbol="US500.cash", action="buy", volume=Decimal("1")),
        submitted_at=old,
    )
    assert result.status == "confirmed" and result.broker_id == "o1"
    assert rpc.get_history_orders_by_time_range.call_args.args[0] < old
    await broker.reconciliation_evidence(datetime.now(UTC))
    assert rpc.get_positions.await_count == 1
    await broker.reconciliation_evidence(old - timedelta(days=5))
    assert rpc.get_positions.await_count == 2


@pytest.mark.asyncio
async def test_exit_comment_matches_own_close_not_unrelated_entry_or_symbol():
    broker, _ = adapter(
        deals=[
            {
                "id": "d1",
                "symbol": "BTCUSDm",
                "clientId": client_id("entry"),
                "brokerComment": client_id("exit") + ":",
                "positionId": "manual-77",
                "entryType": "DEAL_ENTRY_OUT",
            }
        ]
    )
    request = TradeRequest(
        account_id="a", symbol="BTCUSDm", action="close_position", position_id="manual-77"
    )
    assert (await broker.reconcile("exit", request)).broker_id == "d1"
    assert (
        await broker.reconcile("entry", request.model_copy(update={"position_id": "other"}))
    ).status == "ambiguous"
    assert (
        await broker.reconcile("exit", request.model_copy(update={"symbol": "BTCUSD"}))
    ).status == "ambiguous"
    assert (await broker.reconcile("not-sent", request)).status == "ambiguous"


@pytest.mark.asyncio
async def test_paginated_history_requires_complete_synchronization():
    broker, rpc = adapter()
    rpc.get_deals_by_time_range.side_effect = [
        {"deals": [{"id": str(i)} for i in range(1000)]},
        {"deals": [{"id": "last"}]},
    ]
    _, deals, _ = await broker.reconciliation_evidence()
    assert len(deals) == 1001
    assert rpc.get_deals_by_time_range.call_args.args[2:] == (1000, 1000)
    broker.evidence = None
    rpc.get_deals_by_time_range.side_effect = None
    rpc.get_deals_by_time_range.return_value = {"deals": [], "synchronizing": True}
    with pytest.raises(LonoraError, match="broker_history_synchronizing"):
        await broker.reconciliation_evidence()
    assert broker.evidence is None
    rpc.get_deals_by_time_range.return_value = {"deals": [{"id": str(i)} for i in range(1000)]}
    with pytest.raises(LonoraError, match="broker_history_limit"):
        await broker.reconciliation_evidence()


@pytest.mark.asyncio
async def test_naive_time_is_rejected_and_absence_never_proves_failure():
    broker, rpc = adapter()
    with pytest.raises(LonoraError, match="broker_reconciliation_time_invalid"):
        await broker.reconciliation_evidence(datetime(2026, 1, 1))
    rpc.get_positions.assert_not_awaited()
    assert (await broker.reconcile("missing")).status == "ambiguous"


@pytest.mark.asyncio
async def test_cancelled_market_order_is_not_a_fill_but_exact_rejection_is_final():
    broker, rpc = adapter(
        orders=[
            {
                "id": "cancelled",
                "symbol": "EURUSDm",
                "clientId": client_id("market"),
                "state": "ORDER_STATE_CANCELED",
            }
        ]
    )
    request = TradeRequest(account_id="a", symbol="EURUSDm", action="buy", volume=Decimal("0.1"))
    assert (await broker.reconcile("market", request)).status == "ambiguous"
    broker.evidence = None
    rpc.get_history_orders_by_time_range.return_value = {
        "historyOrders": [
            {
                "id": "rejected",
                "symbol": "EURUSDm",
                "clientId": client_id("market"),
                "state": "ORDER_STATE_REJECTED",
            }
        ]
    }
    result = await broker.reconcile("market", request)
    assert result.status == "failed" and result.code == "broker_order_rejected"
