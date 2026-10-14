"""Official SDK signature/retcode/stream callback fixtures. No live broker requests."""

import asyncio
import importlib
import inspect
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Quote
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_trading.retcodes import normalize_response


async def main() -> None:
    closing = asyncio.Event()
    release = asyncio.Event()
    close_count = 0

    async def close_fixture() -> None:
        nonlocal close_count
        close_count += 1
        closing.set()
        await release.wait()

    manager = BrokerManager(None, None)  # type: ignore[arg-type]
    closing_broker = cast(BrokerAdapter, SimpleNamespace(close=close_fixture))
    manager.connections["fixture"] = (1, closing_broker)
    shutdown = asyncio.create_task(manager.close())
    await closing.wait()
    acquisition = asyncio.create_task(manager.get("owner", "fixture"))
    await asyncio.sleep(0)
    assert not acquisition.done()
    release.set()
    await shutdown
    try:
        await acquisition
    except LonoraError as error:
        assert error.code == "broker_connection_unavailable"
    else:
        raise AssertionError("shutdown allowed a new broker acquisition")
    await manager.close()
    assert close_count == 1 and not manager.connections
    print(
        "PASS concurrent broker shutdown fences late acquisition and repeated close is idempotent"
    )
    sdk_rpc: Any = importlib.import_module(
        "metaapi_cloud_sdk.metaapi.rpc_metaapi_connection_instance"
    ).RpcMetaApiConnectionInstance
    trade_exception: Any = importlib.import_module(
        "metaapi_cloud_sdk.clients.metaapi.trade_exception"
    ).TradeException
    calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
    response: dict[str, Any] = {"stringCode": "ERR_NO_ERROR", "numericCode": 0, "orderId": "42"}
    failure: Exception | None = None
    authorized = 0

    def method(name: str):
        async def invoke(*args: Any, **kwargs: Any) -> dict[str, Any]:
            inspect.signature(getattr(sdk_rpc, name)).bind(None, *args, **kwargs)
            calls.append((name, args, kwargs))
            if failure:
                raise failure
            return response

        return invoke

    names = [
        "create_market_buy_order",
        "create_market_sell_order",
        "create_limit_buy_order",
        "create_limit_sell_order",
        "create_stop_buy_order",
        "create_stop_sell_order",
        "modify_order",
        "modify_position",
        "cancel_order",
        "close_position",
    ]
    rpc = SimpleNamespace(
        **{name: method(name) for name in names},
        get_orders=AsyncMock(
            return_value=[
                {"id": "42", "symbol": "XAUUSD.a", "type": "ORDER_TYPE_BUY_LIMIT", "openPrice": 99}
            ]
        ),
    )
    broker = object.__new__(MetaApiBroker)

    async def authorize() -> None:
        nonlocal authorized
        authorized += 1

    with patch.object(MetaApiBroker, "prepare", AsyncMock(return_value=rpc)):
        broker.account_id = "opaque-metaapi-transport-id"
        broker.connection_id = "internal-routing-id"
        broker.account_instance = SimpleNamespace(
            login="24680", server="Native-Demo", version=5, name="Integration friendly name"
        )
        rpc.get_account_information = AsyncMock(
            return_value={"currency": "USD", "balance": 1000, "equity": 1000}
        )
        native_account = await broker.account()
        assert native_account.id == "internal-routing-id" and native_account.login == "24680"
        assert native_account.server == "Native-Demo" and native_account.platform == "mt5"
        assert native_account.broker is None and native_account.name is None
        print(
            "PASS real SDK entity login/server/MetaTrader-version fallback does not invent a broker name or expose transport UUID as native login"
        )
        for action, native in zip(
            ("buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"),
            names[:6],
            strict=True,
        ):
            request = TradeRequest(
                account_id="fixture",
                operation_id=action,
                action=action,
                symbol="XAUUSD.a",
                volume=Decimal("0.1"),
                price=Decimal(99) if action not in {"buy", "sell"} else None,
            )
            result = await broker.execute(request, authorize)
            assert result.status == "confirmed" and calls[-1][0] == native
            assert calls[-1][1][0] == "XAUUSD.a"
        assert authorized == 6
        print(
            "PASS six actual SDK order method signatures preserve exact symbols and MT4 ERR_NO_ERROR/numeric zero confirms success"
        )
        response = {"stringCode": "TRADE_RETCODE_DONE", "numericCode": 10009}
        result = await broker.execute(
            TradeRequest(
                account_id="fixture",
                action="modify_order",
                symbol="XAUUSD.a",
                order_id="42",
                stop_loss=Decimal(98),
            ),
            authorize,
        )
        assert result.status == "confirmed" and result.broker_id == "42"
        assert calls[-1] == ("modify_order", ("42", 99.0), {"stop_loss": 98.0, "take_profit": None})
        await broker.execute(
            TradeRequest(
                account_id="fixture",
                action="modify_order",
                symbol="XAUUSD.a",
                order_id="42",
                clear_take_profit=True,
            ),
            authorize,
        )
        assert calls[-1][2]["take_profit"] == 0.0 and calls[-1][2]["stop_loss"] is None
        await broker.execute(
            TradeRequest(
                account_id="fixture", action="cancel_order", symbol="XAUUSD.a", order_id="42"
            ),
            authorize,
        )
        assert calls[-1][0] == "cancel_order" and calls[-1][1] == ("42",)
        print(
            "PASS pending edits preserve omitted fields/entry price, explicit clear uses SDK zero, and cancel uses the real order ticket"
        )
        request = TradeRequest(
            account_id="fixture",
            action="buy_limit",
            symbol="XAUUSD.a",
            volume=Decimal("0.1"),
            price=Decimal(99),
        )
        failure = trade_exception("Scripted broker rejection", 130, "ERR_INVALID_STOPS")
        assert (await broker.execute(request, authorize)).status == "failed"
        failure = trade_exception("Scripted broker timeout", 128, "ERR_TRADE_TIMEOUT")
        assert (await broker.execute(request, authorize)).status == "ambiguous"
        failure = TimeoutError("Scripted lost response")
        assert (await broker.execute(request, authorize)).status == "ambiguous"
        assert normalize_response("ERR_NO_ERROR", 130) == "ambiguous"
        print(
            "PASS known SDK broker rejections are failed; timeouts and contradictory response codes remain ambiguous without resend"
        )

    # Streaming fixtures drive the actual SDK listener hook, alongside an existing
    # quote subscription. No OHLC is derived from the tick/quote side.
    listeners: list[Any] = []
    subscriptions: list[tuple[str, list[dict[str, Any]]]] = []
    unsubscriptions: list[tuple[str, list[dict[str, Any]]]] = []

    async def subscribe(symbol: str, specs: list[dict[str, Any]]) -> None:
        subscriptions.append((symbol, specs))
        for listener in list(listeners):
            if specs[0]["type"] == "candles":
                await listener.on_candles_updated(
                    "0",
                    [
                        {
                            "symbol": "WRONG.a",
                            "timeframe": "5m",
                            "time": "2026-10-14T00:00:00Z",
                            "open": 10,
                            "high": 15,
                            "low": 9,
                            "close": 12,
                        },
                        {
                            "symbol": symbol,
                            "timeframe": "1h",
                            "time": "2026-10-14T00:00:00Z",
                            "open": 10,
                            "high": 15,
                            "low": 9,
                            "close": 12,
                        },
                        {
                            "symbol": symbol,
                            "timeframe": "5m",
                            "time": "2026-10-14T00:00:00Z",
                            "open": 100,
                            "high": 111,
                            "low": 95,
                            "close": 107,
                        },
                    ],
                )

    async def unsubscribe(symbol: str, specs: list[dict[str, Any]]) -> None:
        unsubscriptions.append((symbol, specs))

    stream = SimpleNamespace(
        add_synchronization_listener=listeners.append,
        remove_synchronization_listener=listeners.remove,
        wait_synchronized=AsyncMock(),
        subscribe_to_market_data=subscribe,
        unsubscribe_from_market_data=unsubscribe,
    )
    stream_broker = object.__new__(MetaApiBroker)
    stream_broker.streaming = stream
    stream_broker.stream_lock = asyncio.Lock()
    stream_broker.account_instance = SimpleNamespace()
    with (
        patch.object(MetaApiBroker, "resolve_account", AsyncMock(return_value=SimpleNamespace())),
        patch.object(MetaApiBroker, "prepare", AsyncMock(return_value=SimpleNamespace())),
        patch.object(MetaApiBroker, "prepare_stream", AsyncMock(return_value=stream)),
        patch.object(
            MetaApiBroker,
            "quote",
            AsyncMock(
                return_value=Quote(
                    symbol="XAUUSD.a",
                    bid=Decimal(100),
                    ask=Decimal(101),
                    observed_at=utcnow(),
                    source="explicit-sdk-fixture",
                )
            ),
        ),
    ):
        quotes = stream_broker.stream_quotes("XAUUSD.a")
        await anext(quotes)
        bars = stream_broker.stream_candles("XAUUSD.a", "5m")
        try:
            bar = await anext(bars)
            assert bar.symbol == "XAUUSD.a" and bar.timeframe == "5m"
            assert (bar.open, bar.high, bar.low, bar.close) == (100, 111, 95, 107)
        finally:
            await bars.aclose()
        assert len(listeners) == 1
        assert unsubscriptions == [("XAUUSD.a", [{"type": "candles", "timeframe": "5m"}])]
        await listeners[0].on_symbol_prices_updated(
            "0", [{"symbol": "XAUUSD.a", "bid": 120, "ask": 121, "time": utcnow()}]
        )
        assert (await anext(quotes)).bid == 120 and bar.close == 107
        await quotes.aclose()
    assert subscriptions == [
        ("XAUUSD.a", [{"type": "quotes"}]),
        ("XAUUSD.a", [{"type": "candles", "timeframe": "5m"}]),
    ]
    assert unsubscriptions[-1] == ("XAUUSD.a", [{"type": "quotes"}]) and not listeners
    print(
        "PASS official candle listener emits only exact authoritative OHLC and cleans up only its own candle subscription"
    )


if __name__ == "__main__":
    asyncio.run(main())
