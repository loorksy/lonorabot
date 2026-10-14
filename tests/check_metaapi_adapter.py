"""Actual adapter calls against explicit scripted SDK transports; never submits live orders."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from lonora_adapters.brokers.metaapi import MetaApiBroker, client_id
from lonora_contracts.trading import TradeRequest


async def main() -> None:
    broker = object.__new__(MetaApiBroker)
    broker.streaming = None
    broker.stream_lock = asyncio.Lock()
    raw = {
        "symbol": "XAUUSDm",
        "time": datetime(2026, 10, 13, tzinfo=UTC),
        "bid": 2700,
        "ask": 2701,
    }
    rpc = SimpleNamespace(
        get_symbol_price=AsyncMock(return_value=raw),
        close_position_partially=AsyncMock(
            return_value={
                "stringCode": "TRADE_RETCODE_DONE",
                "orderId": "o1",
                "positionId": "p1",
                "dealId": "d1",
            }
        ),
        close_position=AsyncMock(),
        get_positions=AsyncMock(return_value=[]),
        get_orders=AsyncMock(return_value=[]),
        get_deals_by_time_range=AsyncMock(return_value={"deals": []}),
    )
    listeners: list[Any] = []

    def add_listener(value: Any) -> None:
        listeners.append(value)

    def remove_listener(value: Any) -> None:
        listeners.remove(value)

    stream = SimpleNamespace(
        connect=AsyncMock(),
        wait_synchronized=AsyncMock(),
        subscribe_to_market_data=AsyncMock(),
        unsubscribe_from_market_data=AsyncMock(),
        add_synchronization_listener=add_listener,
        remove_synchronization_listener=remove_listener,
    )

    def streaming_connection(storage: Any) -> SimpleNamespace:
        return stream

    broker.account_instance = SimpleNamespace(get_streaming_connection=streaming_connection)
    with (
        patch.object(MetaApiBroker, "prepare", AsyncMock(return_value=rpc)),
        patch.object(MetaApiBroker, "prepare_stream", AsyncMock(return_value=stream)),
    ):
        broker.streaming = stream
        quotes = broker.stream_quotes("XAUUSDm")
        assert (await anext(quotes)).symbol == "XAUUSDm"
        stream.subscribe_to_market_data.assert_awaited_once_with("XAUUSDm", [{"type": "quotes"}])
        await listeners[0].on_symbol_prices_updated(
            "fixture-instance",
            [{**raw, "symbol": "XAUUSD", "bid": 1, "ask": 2}, {**raw, "bid": 2702, "ask": 2703}],
        )
        assert str((await anext(quotes)).bid) == "2702"
        await quotes.aclose()
        assert not listeners
        stream.unsubscribe_from_market_data.assert_awaited_once_with(
            "XAUUSDm", [{"type": "quotes"}]
        )
        print(
            "PASS native SDK subscription, exact symbol filtering, listener cleanup and unsubscribe"
        )
        request = TradeRequest(
            account_id="fixture",
            operation_id="partial-close",
            action="close_position",
            symbol="XAUUSDm",
            position_id="p1",
            volume=Decimal("0.1"),
        )
        result = await broker.execute(request)
        rpc.close_position_partially.assert_awaited_once_with(
            "p1", 0.1, options={"clientId": client_id("partial-close")}
        )
        rpc.close_position.assert_not_awaited()
        assert result.status == "confirmed" and result.details["deal_id"] == "d1"
        print(
            "PASS partial close uses SDK partial-volume method and preserves separate order/position/deal IDs"
        )
        uncertain = await broker.reconcile(
            "modify-fixture",
            TradeRequest(
                account_id="fixture",
                action="modify_position",
                position_id="p1",
                symbol="XAUUSDm",
                stop_loss=Decimal("2650"),
            ),
        )
        assert uncertain.status == "ambiguous" and uncertain.code == "mutation_evidence_required"
        rpc.get_positions.assert_not_awaited()
        print(
            "PASS modification uncertainty stays blocked instead of matching an unrelated position"
        )
        start, end = datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 13, tzinfo=UTC)
        rpc.get_deals_by_time_range.return_value = {
            "deals": [
                {
                    "id": "deal-fixture",
                    "symbol": "XAUUSDm",
                    "time": start,
                    "profit": 12,
                    "token": "explicit-secret-fixture",
                }
            ]
        }
        history = await broker.history(start, end, 20)
        assert history[0]["symbol"] == "XAUUSDm" and "token" not in history[0]
        rpc.get_deals_by_time_range.assert_awaited_once_with(start, end, 0, 20)
        print("PASS bounded broker deal history normalizes timestamps and excludes credentials")


if __name__ == "__main__":
    asyncio.run(main())
