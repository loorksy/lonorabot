"""Actual adapter calls against explicit scripted SDK transports; never submits live orders."""

import asyncio
import importlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from lonora_adapters.brokers.metaapi import MetaApiBroker, client_id
from lonora_contracts.trading import TradeRequest
from lonora_tools.symbols import canonical_broker_symbol


async def main() -> None:
    broker = object.__new__(MetaApiBroker)
    broker.streaming = None
    broker.stream_lock = asyncio.Lock()
    raw = {
        "symbol": "XAUUSDm",
        "time": datetime(2026, 10, 13, tzinfo=UTC),
        "bid": 2700,
        "ask": 2701,
        "profitTickValue": "1.2",
        "lossTickValue": "1.25",
        "accountCurrencyExchangeRate": "0.01",
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
        get_history_orders_by_time_range=AsyncMock(return_value={"historyOrders": []}),
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
        initial = await anext(quotes)
        assert initial.symbol == "XAUUSDm"
        assert initial.profit_tick_value == Decimal("1.2")
        assert initial.loss_tick_value == Decimal("1.25")
        assert initial.tick_value_basis == "account_currency_per_lot"
        assert initial.account_currency_exchange_rate == Decimal("0.01")
        stream.subscribe_to_market_data.assert_awaited_once_with("XAUUSDm", [{"type": "quotes"}])
        await listeners[0].on_symbol_prices_updated(
            "fixture-instance",
            [
                {**raw, "symbol": "XAUUSD", "bid": 1, "ask": 2},
                {**raw, "bid": 2702, "ask": 2703, "lossTickValue": "1.3"},
            ],
        )
        updated = await anext(quotes)
        assert str(updated.bid) == "2702"
        assert updated.loss_tick_value == Decimal("1.3")
        assert updated.profit_tick_value == Decimal("1.2")
        assert updated.account_currency_exchange_rate == Decimal("0.01")
        await listeners[0].on_symbol_prices_updated(
            "fixture-instance", [{**raw, "lossTickValue": "NaN", "profitTickValue": None}]
        )
        without_money = await anext(quotes)
        assert without_money.bid == 2700 and without_money.loss_tick_value is None
        assert without_money.profit_tick_value is None and without_money.tick_value_basis is None
        await quotes.aclose()
        assert not listeners
        stream.unsubscribe_from_market_data.assert_awaited_once_with(
            "XAUUSDm", [{"type": "quotes"}]
        )
        print(
            "PASS native SDK subscription, exact symbol filtering, listener cleanup and unsubscribe"
        )
        print(
            "PASS RPC and live price callbacks retain tick money without FX multiplication; invalid economics do not stop prices"
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
        tag = client_id("partial-close")
        assert len(tag) <= 31 and tag.startswith("LN_") and tag.count("_") == 2
        rpc.close_position_partially.assert_awaited_once_with("p1", 0.1, options={"clientId": tag})
        rpc.close_position.assert_not_awaited()
        assert result.status == "confirmed" and result.details["deal_id"] == "d1"
        print(
            "PASS partial close uses SDK partial-volume method and preserves separate order/position/deal IDs"
        )
        validation_exception: Any = importlib.import_module(
            "metaapi_cloud_sdk.clients.error_handler"
        ).ValidationException
        rpc.create_market_buy_order = AsyncMock(
            side_effect=validation_exception(
                "Validation failed", [{"parameter": "clientId", "message": "Invalid value"}]
            )
        )
        rejected = await broker.execute(
            TradeRequest(
                account_id="fixture",
                operation_id="rejected-shape",
                action="buy",
                symbol="XAUUSDm",
                volume=Decimal("0.1"),
            )
        )
        assert rejected.status == "failed" and rejected.code == "broker_request_rejected"
        print("PASS a rejected trade request stays failed instead of becoming an uncertain receipt")
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
        rpc.get_deals_by_time_range.reset_mock()
        rpc.get_history_orders_by_time_range.return_value = {
            "historyOrders": [],
            "synchronizing": False,
        }
        rpc.get_positions.return_value = [
            {"id": "p7", "symbol": "XAUUSDm", "clientId": client_id("observed-buy")}
        ]
        buy = TradeRequest(
            account_id="fixture", action="buy", symbol="XAUUSDm", volume=Decimal("0.1")
        )
        observed = await broker.reconcile("observed-buy", buy)
        missing = await broker.reconcile("missing-buy", buy)
        assert observed.status == "confirmed" and missing.code == "execution_not_observed"
        assert rpc.get_positions.await_count == 1
        assert rpc.get_deals_by_time_range.await_count == 1
        await broker.execute(request)
        await broker.reconcile("missing-buy", buy)
        assert rpc.get_positions.await_count == 2
        print(
            "PASS one broker snapshot serves every uncertain operation in a pass and refreshes after a send"
        )


async def streamed_market_state() -> None:
    broker = object.__new__(MetaApiBroker)
    quiet_time = datetime.now(UTC) - timedelta(hours=2)
    quiet = {
        "symbol": "ABTm",
        "bid": 102.13,
        "ask": 102.22,
        "time": quiet_time,
        "profitTickValue": "2.4",
        "lossTickValue": "2.5",
        "accountCurrencyExchangeRate": "7.52",
    }
    specifications = [
        {
            "symbol": "XAUUSDm",
            "digits": 3,
            "tickSize": 0.001,
            "minVolume": 0.01,
            "maxVolume": 200,
            "volumeStep": 0.01,
        },
        {
            "symbol": "ABTm",
            "digits": 2,
            "tickSize": 0.01,
            "minVolume": 1,
            "maxVolume": 1000,
            "volumeStep": 1,
            "contractSize": "123.4",
            "baseCurrency": "XYZ",
            "profitCurrency": "USC",
        },
    ]

    def specification(symbol: str) -> dict[str, Any] | None:
        return next((item for item in specifications if item["symbol"] == symbol), None)

    def price(symbol: str) -> dict[str, Any] | None:
        return quiet if symbol == "ABTm" else None

    subscriptions = {"ABTm": [{"type": "quotes"}]}
    shared = SimpleNamespace(synchronized=True, _closed=False)
    broker.streaming = SimpleNamespace(
        _meta_api_connection=shared,
        terminal_state=SimpleNamespace(
            specifications=specifications, specification=specification, price=price
        ),
        subscriptions=subscriptions.get,
    )
    rpc = SimpleNamespace(
        get_symbols=AsyncMock(return_value=["XAUUSDm"]),
        get_symbol_specification=AsyncMock(),
        get_symbol_price=AsyncMock(
            return_value={**quiet, "time": datetime.now(UTC), "lossTickValue": "3.75"}
        ),
    )
    with patch.object(MetaApiBroker, "prepare", AsyncMock(return_value=rpc)):
        assert await broker.symbols() == ["ABTm", "XAUUSDm"]
        contract = await broker.instrument("ABTm")
        assert contract.volume_min == 1
        assert contract.contract_size == Decimal("123.4")
        assert contract.base_currency == "XYZ" and contract.profit_currency == "USC"
        assert [item.symbol for item in await broker.instruments()] == ["ABTm", "XAUUSDm"]
        quiet_quote = await broker.quote("ABTm")
        assert quiet_quote.observed_at == quiet_time
        assert quiet_quote.loss_tick_value == Decimal("2.5")
        assert quiet_quote.profit_tick_value == Decimal("2.4")
        assert quiet_quote.tick_value_basis == "account_currency_per_lot"
        assert quiet_quote.account_currency_exchange_rate == Decimal("7.52")
        rpc.get_symbols.assert_not_awaited()
        rpc.get_symbol_specification.assert_not_awaited()
        rpc.get_symbol_price.assert_not_awaited()
        print(
            "PASS synchronized streaming state serves symbols, specifications and quiet subscribed quotes without RPC credits"
        )
        del subscriptions["ABTm"]
        rpc_quote = await broker.quote("ABTm")
        assert rpc_quote.observed_at > quiet_time
        assert rpc_quote.loss_tick_value == Decimal("3.75")
        assert rpc_quote.account_currency_exchange_rate == Decimal("7.52")
        rpc.get_symbol_price.assert_awaited_once_with("ABTm")
        shared.synchronized = False
        assert await broker.symbols() == ["XAUUSDm"]
        rpc.get_symbols.assert_awaited_once()
        print("PASS stale unsubscribed prices and unsynchronized state still use broker RPC")
        print(
            "PASS synchronized and RPC quote economics share broker-account units and preserve instrument metadata"
        )


async def symbol_case() -> None:
    class Catalog:
        async def symbols(self) -> list[str]:
            return ["XAUUSDm", "EURUSDm"]

    assert await canonical_broker_symbol(Catalog(), "XAUUSDM") == "XAUUSDm"
    assert await canonical_broker_symbol(Catalog(), "XAUUSD") == "XAUUSD"
    print("PASS a unique broker symbol matches ignoring letter case")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(streamed_market_state())
    asyncio.run(symbol_case())
