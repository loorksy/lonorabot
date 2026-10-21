import asyncio
import importlib
import logging
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from urllib.parse import urlparse

import httpx
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.chart_controller import validate_timeframe
from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import broker_operation_tag
from pydantic import ValidationError

from . import normalize
from .metaapi_discovery import update_domain
from .metaapi_lifecycle import (
    ConnectionSlot,
    closed_error,
    history_storage,
    is_closed,
    synchronized,
)

log = logging.getLogger("lonora.metaapi")
EVIDENCE_SECONDS = 15


def provider_error(error: Exception, stage: str) -> LonoraError:
    if isinstance(error, LonoraError):
        return error
    status = getattr(error, "status_code", None)
    if status == 404:
        message = str(error).split("Request URL:", 1)[0].casefold()
        missing = any(
            term in message for term in ("not found", "unknown", "does not exist", "not exist")
        )
        if stage != "candles" or "account" in message and missing:
            return LonoraError("broker_account_not_found", 404)
        if "symbol" in message and missing:
            return LonoraError("symbol_not_found", 404)
        return LonoraError("broker_candles_not_found", 404)
    if status in {401, 403}:
        return LonoraError("broker_credentials_rejected", 409)
    if status == 429:
        return LonoraError("broker_rate_limited", 429)
    if (
        isinstance(error, (TimeoutError, httpx.TimeoutException))
        or "Timeout" in type(error).__name__
    ):
        return LonoraError(
            "broker_candles_timeout" if stage == "candles" else "broker_connection_timeout", 504
        )
    if isinstance(error, ValidationError):
        return LonoraError("broker_candles_invalid", 502)
    if status == 400:
        return LonoraError(
            "broker_candles_request_rejected" if stage == "candles" else "broker_request_rejected",
            422,
        )
    return LonoraError(
        "broker_candles_unavailable" if stage == "candles" else "broker_connection_unavailable", 502
    )


def sdk_number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    converted = float(value)
    if not value.is_finite() or Decimal(str(converted)) != value:
        raise LonoraError("broker_numeric_precision_loss")
    return converted


def client_id(operation_id: str) -> str:
    return broker_operation_tag(operation_id)


def validate_sdk_url(url: str) -> str:
    parsed = urlparse(url)
    if (
        parsed.scheme not in {"https", "wss"}
        or not parsed.hostname
        or not parsed.hostname.endswith(".agiliumtrade.ai")
        or parsed.username
        or parsed.password
        or parsed.port not in {None, 443}
    ):
        raise LonoraError("broker_endpoint_forbidden", 403)
    return url


def proxy_session() -> Any:
    aiohttp: Any = importlib.import_module("aiohttp")
    session = aiohttp.ClientSession(trust_env=True)
    original_connect = session.ws_connect

    def connect(url: str, **options: Any) -> Any:
        validate_sdk_url(str(url))
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        if proxy:
            options["proxy"] = proxy
        return original_connect(url, **options)

    session.ws_connect = connect
    return session


def configure_sdk_transport() -> None:
    """Keep official SDK domain discovery and route its transports through inherited proxies."""
    socketio: Any = importlib.import_module("socketio")
    http_module: Any = importlib.import_module("metaapi_cloud_sdk.clients.http_client")
    websocket_module: Any = importlib.import_module(
        "metaapi_cloud_sdk.clients.metaapi.metaapi_websocket_client"
    )
    domain_module: Any = importlib.import_module("metaapi_cloud_sdk.clients.domain_client")
    if getattr(http_module, "_lonora_transport_configured", False):
        return

    async def request(client: Any, options: dict[str, Any]) -> httpx.Response:
        url = validate_sdk_url(options["url"])
        async with httpx.AsyncClient(timeout=client._timeout, follow_redirects=False) as transport:
            return await transport.request(
                options.get("method", "GET"),
                url,
                params=options.get("params"),
                headers=options.get("headers"),
                json=options.get("body"),
                files=options.get("files"),
            )

    class ProxySocketClient(socketio.AsyncClient):
        async def connect(self, url: str, *args: Any, **kwargs: Any) -> Any:
            validate_sdk_url(url)
            if self.eio.state == "disconnected":
                # Engine.IO closes the previous session from a background task when a
                # connection resets. The SDK reconnects immediately, so reusing that session
                # cancels the new handshake mid-flight.
                previous = self.eio.http
                self.eio.http = proxy_session()
                if previous is not None and not previous.closed:
                    await previous.close()
            return await socketio.AsyncClient.connect(self, url, *args, **kwargs)

    original_reconnect = websocket_module.MetaApiWebsocketClient._reconnect

    async def reconnect(
        client: Any, instance_number: int, socket_instance_index: int, region: str
    ) -> None:
        while True:
            try:
                return await original_reconnect(
                    client, instance_number, socket_instance_index, region
                )
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is None or task.cancelling():
                    raise
                # A cancelled transport future, not a cancelled owner. Socket.IO runs this
                # from its disconnect handler and swallows the cancellation, which would
                # leave isReconnecting set and the socket permanently disconnected.
                try:
                    instances = client._socket_instances[region][instance_number]
                    instances[socket_instance_index]["isReconnecting"] = False
                except (KeyError, IndexError):
                    return

    http_module.HttpClient._make_request = request
    domain_module.DomainClient._update_domain = update_domain
    websocket_module.socketio = SimpleNamespace(AsyncClient=ProxySocketClient)
    websocket_module.MetaApiWebsocketClient._reconnect = reconnect
    http_module._lonora_transport_configured = True


class MetaApiBroker:
    def __init__(
        self, account_id: str, region: str | None, token: str, connection_id: str | None = None
    ):
        configure_sdk_transport()
        sdk: Any = importlib.import_module("metaapi_cloud_sdk")
        self.api: Any = sdk.MetaApi(
            token,
            {
                **({"region": region} if region else {}),
                "requestTimeout": 20,
                "connectTimeout": 20,
                "historicalMarketDataRequestTimeout": 30,
                "retryOpts": {"retries": 0},
                "enableSocketioDebugger": False,
                "packetLogger": {"enabled": False},
            },
        )
        self.account_id = account_id
        self.connection_id = connection_id
        self._log_redactions = (token, account_id)
        self.account_instance: Any = None
        self.rpc: Any = None
        self.streaming: Any = None
        self.stream_lock = asyncio.Lock()
        self.lock = asyncio.Lock()
        self.account_lock = asyncio.Lock()
        self.rpc_slot = ConnectionSlot("rpc")
        self.stream_slot = ConnectionSlot("streaming")
        self.evidence: (
            tuple[float, datetime, list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
            | None
        ) = None
        self.evidence_lock = asyncio.Lock()
        self._closing = False

    def diagnose(self, error: Exception, stage: str) -> LonoraError:
        if isinstance(error, LonoraError) and error.diagnostic_message:
            return error
        failure = provider_error(error, stage)
        failure.diagnostic_type = type(error).__name__
        failure.diagnostic_message = safe_exception_message(
            error, getattr(self, "_log_redactions", ())
        )
        log.warning(
            "broker_%s_failed code=%s type=%s message=%s",
            stage,
            failure.code,
            type(error).__name__,
            failure.diagnostic_message,
        )
        return failure

    async def resolve_account(self) -> Any:
        # Historical REST data needs the account's own region, not an RPC lease.
        async with self.account_lock:
            if self.account_instance is None:
                try:
                    async with asyncio.timeout(25):
                        self.account_instance = await self.api.metatrader_account_api.get_account(
                            self.account_id
                        )
                except Exception as error:
                    raise self.diagnose(error, "account") from error
            return self.account_instance

    def _slot(self, kind: str) -> ConnectionSlot:
        # Some scripted adapter tests instantiate without __init__.
        name = "rpc_slot" if kind == "rpc" else "stream_slot"
        if not hasattr(self, name):
            setattr(self, name, ConnectionSlot(kind))
        return getattr(self, name)

    async def _discard_locked(self, kind: str, connection: Any) -> None:
        attr = "rpc" if kind == "rpc" else "streaming"
        if getattr(self, attr, None) is not connection:
            return
        setattr(self, attr, None)
        shared = getattr(connection, "_meta_api_connection", None)
        account: Any = getattr(self, "account_instance", None)
        registry = getattr(account, "_connection_registry", None)
        # close() removes the SDK registry when this owned instance is the last user.
        try:
            async with asyncio.timeout(5):
                if kind == "rpc" and shared is not None:
                    # SDK RpcMetaApiConnectionInstance.close schedules shared.close
                    # without awaiting it. Await ownership release before registry reuse,
                    # or that late task could remove the replacement connection.
                    connection._closed = True
                    await shared.close(connection.instance_id)
                else:
                    await connection.close()
        except Exception as error:
            self.diagnose(error, "connection_cleanup")
        if shared is not None:
            shared._closed = True
        if registry is not None and shared is not None:
            entries = getattr(registry, "_" + kind + "_connections", {})
            # A closed instance's close() is a no-op. The shared closed connection may
            # still be registered; remove it before requesting another SDK wrapper.
            if entries.get(account.id) is shared:
                try:
                    async with asyncio.timeout(5):
                        await getattr(registry, "remove_" + kind)(account)
                except Exception as error:
                    self.diagnose(error, "connection_cleanup")
                    if entries.get(account.id) is shared:
                        entries.pop(account.id, None)
                        getattr(registry, "_" + kind + "_connection_instances", {}).pop(
                            account.id, None
                        )

    async def invalidate(self, kind: str, connection: Any) -> None:
        lock = self.lock if kind == "rpc" else self.stream_lock
        async with lock:
            await self._discard_locked(kind, connection)

    async def _prepare_connection(self, kind: str) -> Any:
        if getattr(self, "_closing", False):
            raise LonoraError("broker_connection_closed", 503)
        attr = "rpc" if kind == "rpc" else "streaming"
        existing = getattr(self, attr, None)
        slot = self._slot(kind)
        if (
            existing is not None
            and not is_closed(existing)
            and synchronized(existing, kind)
            and (slot.task is None or slot.task.done())
        ):
            return existing

        async def create() -> Any:
            try:
                account = await self.resolve_account()
            except Exception as error:
                failure = self.diagnose(error, kind)
                slot.failed(failure)
                raise failure from error
            lock = self.lock if kind == "rpc" else self.stream_lock
            async with lock:
                connection = getattr(self, attr, None)
                if connection is not None and is_closed(connection):
                    await self._discard_locked(kind, connection)
                    connection = None
                try:
                    async with asyncio.timeout(25):
                        if connection is None:
                            connection = (
                                account.get_rpc_connection()
                                if kind == "rpc"
                                else account.get_streaming_connection(history_storage())
                            )
                            setattr(self, attr, connection)
                            await connection.connect()
                        if not synchronized(connection, kind):
                            if kind == "rpc":
                                await connection.wait_synchronized(timeout_in_seconds=15)
                            else:
                                await connection.wait_synchronized({"timeoutInSeconds": 15})
                    slot.ready()
                    return connection
                except Exception as error:
                    if connection is not None:
                        await self._discard_locked(kind, connection)
                    failure = self.diagnose(error, kind)
                    slot.failed(failure)
                    raise failure from error

        return await slot.get(create)

    async def prepare(self) -> Any:
        return await self._prepare_connection("rpc")

    async def prepare_stream(self) -> Any:
        return await self._prepare_connection("streaming")

    async def read_rpc(self, method: str, *args: Any) -> Any:
        # Read-only calls can be repeated once after a definitively closed connection.
        # Never use this helper for a financial mutation.
        for attempt in range(2):
            rpc = await self.prepare()
            try:
                return await getattr(rpc, method)(*args)
            except Exception as error:
                if closed_error(error) or is_closed(rpc):
                    await self.invalidate("rpc", rpc)
                    if attempt == 0:
                        continue
                raise self.diagnose(error, "rpc") from error
        raise LonoraError("broker_connection_unavailable", 502)

    def synchronized_terminal(self) -> Any:
        stream = getattr(self, "streaming", None)
        if stream is None or is_closed(stream) or not synchronized(stream, "streaming"):
            return None
        return getattr(stream, "terminal_state", None)

    def streamed_specifications(self) -> list[dict[str, Any]]:
        # Synchronized streaming state is free; RPC symbol reads cost broker CPU credits
        # (500 for get_symbols, 50 per specification).
        terminal = self.synchronized_terminal()
        if terminal is None:
            return []
        specifications: list[dict[str, Any]] = terminal.specifications or []
        return [dict(value) for value in specifications]

    async def symbols(self) -> list[str]:
        try:
            streamed = self.streamed_specifications()
            if streamed:
                return sorted(str(value["symbol"]) for value in streamed)
            return sorted(await self.read_rpc("get_symbols"))
        except Exception as error:
            raise self.diagnose(error, "symbols") from error

    async def instrument(self, symbol: str) -> Instrument:
        try:
            terminal = self.synchronized_terminal()
            streamed = terminal.specification(symbol) if terminal is not None else None
            result = normalize.instrument(
                dict(streamed)
                if streamed
                else await self.read_rpc("get_symbol_specification", symbol)
            )
            if result.symbol != symbol:
                raise ValueError("broker_symbol_mismatch")
            return result
        except Exception as error:
            raise self.diagnose(error, "instrument") from error

    async def instruments(self) -> list[Instrument]:
        try:
            streamed = self.streamed_specifications()
            if not streamed:
                try:
                    # One streaming synchronization replaces one RPC per symbol, which
                    # exhausts the per-account quota on brokers with hundreds of symbols.
                    await self.prepare_stream()
                    streamed = self.streamed_specifications()
                except LonoraError:
                    streamed = []
            if streamed:
                return sorted(
                    (normalize.instrument(value) for value in streamed[:2000]),
                    key=lambda instrument: instrument.symbol,
                )
            symbols = await self.read_rpc("get_symbols")
            if len(symbols) > 2000:
                symbols = symbols[:2000]
            result: list[Instrument] = []
            semaphore = asyncio.Semaphore(8)

            async def read(symbol: str) -> None:
                async with semaphore:
                    value = await self.read_rpc("get_symbol_specification", symbol)
                    result.append(normalize.instrument(value))

            await asyncio.gather(*(read(symbol) for symbol in symbols))
            return sorted(result, key=lambda instrument: instrument.symbol)
        except Exception as error:
            raise self.diagnose(error, "instruments") from error

    async def stream_quotes(self, symbol: str) -> AsyncGenerator[Quote, None]:
        # SDK streaming is shared by symbol listeners and survives without a browser.
        queue: asyncio.Queue[Quote] = asyncio.Queue(maxsize=1)
        listener_base: Any = importlib.import_module(
            "metaapi_cloud_sdk.clients.metaapi.synchronization_listener"
        ).SynchronizationListener

        async def prices(
            listener: Any,
            instance_index: str,
            values: list[dict[str, Any]],
            *args: Any,
            **kwargs: Any,
        ) -> None:
            for value in values:
                if value.get("symbol") != symbol:
                    continue
                try:
                    quote = normalize.quote(value)
                except (ValueError, KeyError):
                    continue
                if queue.full():
                    queue.get_nowait()
                queue.put_nowait(quote)

        listener: Any = type(
            "LonoraPriceListener",
            (listener_base,),
            {
                "on_symbol_prices_updated": prices,
            },
        )()
        stream = await self.prepare_stream()
        stream.add_synchronization_listener(listener)
        try:
            await stream.subscribe_to_market_data(symbol, [{"type": "quotes"}])
            yield await self.quote(symbol)
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=30)
                except TimeoutError:
                    # Verify synchronization and resubscribe after SDK reconnects. A fresh
                    # RPC observation provides recovery; never synthesize price/timestamps.
                    if is_closed(stream):
                        raise Exception(
                            "This connection has been closed, please create a new connection"
                        ) from None
                    if not synchronized(stream, "streaming"):
                        async with asyncio.timeout(20):
                            await stream.wait_synchronized({"timeoutInSeconds": 15})
                    await stream.subscribe_to_market_data(symbol, [{"type": "quotes"}])
                    yield await self.quote(symbol)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failure = self.diagnose(error, "streaming")
            if (
                closed_error(error)
                or is_closed(stream)
                or (not synchronized(stream, "streaming") and failure.status == 504)
            ):
                await self.invalidate("streaming", stream)
                self._slot("streaming").failed(failure)
            raise failure from error
        finally:
            stream.remove_synchronization_listener(listener)
            # This generator is the sole resident consumer of this exact symbol.
            try:
                if stream is self.streaming and not is_closed(stream):
                    await stream.unsubscribe_from_market_data(symbol, [{"type": "quotes"}])
            except Exception:
                pass

    async def stream_candles(self, symbol: str, timeframe: str) -> AsyncGenerator[Candle, None]:
        validate_timeframe(timeframe)
        queue: asyncio.Queue[Candle | LonoraError] = asyncio.Queue(maxsize=1000)
        listener_base: Any = importlib.import_module(
            "metaapi_cloud_sdk.clients.metaapi.synchronization_listener"
        ).SynchronizationListener

        async def updated(
            listener: Any,
            instance_index: str,
            values: list[dict[str, Any]],
            *args: Any,
            **kwargs: Any,
        ) -> None:
            for value in values:
                if value.get("symbol") != symbol or value.get("timeframe") != timeframe:
                    continue
                try:
                    candle = normalize.candle(value, symbol, timeframe)
                except (ValueError, KeyError):
                    continue
                if queue.full():
                    queue.get_nowait()
                    queue.put_nowait(LonoraError("broker_candle_stream_overflow", 502))
                    return
                queue.put_nowait(candle)

        listener: Any = type(
            "LonoraCandleListener", (listener_base,), {"on_candles_updated": updated}
        )()
        subscription = [{"type": "candles", "timeframe": timeframe}]
        stream = await self.prepare_stream()
        stream.add_synchronization_listener(listener)
        try:
            await stream.subscribe_to_market_data(symbol, subscription)
            while True:
                try:
                    candle = await asyncio.wait_for(queue.get(), timeout=30)
                    if isinstance(candle, LonoraError):
                        raise candle
                    yield candle
                except TimeoutError:
                    if is_closed(stream):
                        raise Exception(
                            "This connection has been closed, please create a new connection"
                        ) from None
                    if not synchronized(stream, "streaming"):
                        async with asyncio.timeout(20):
                            await stream.wait_synchronized({"timeoutInSeconds": 15})
                    await stream.subscribe_to_market_data(symbol, subscription)
                    # Recovery is exact broker history, never OHLC inferred from quotes.
                    for candle in await self.candles(symbol, timeframe, 2):
                        yield candle
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failure = self.diagnose(error, "candles")
            if (
                closed_error(error)
                or is_closed(stream)
                or (not synchronized(stream, "streaming") and failure.status == 504)
            ):
                await self.invalidate("streaming", stream)
                self._slot("streaming").failed(failure)
            raise failure from error
        finally:
            stream.remove_synchronization_listener(listener)
            try:
                if stream is self.streaming and not is_closed(stream):
                    await stream.unsubscribe_from_market_data(symbol, subscription)
            except Exception:
                pass

    async def quote(self, symbol: str) -> Quote:
        # A synchronized SDK price is authoritative. Do not make a working price
        # stream depend on a separate RPC application finishing startup.
        stream = getattr(self, "streaming", None)
        if stream is not None and not is_closed(stream) and synchronized(stream, "streaming"):
            terminal = getattr(stream, "terminal_state", None)
            if terminal is not None:
                value = terminal.price(symbol)
                if value:
                    observed = normalize.observed(value["time"])
                    age = (datetime.now(UTC) - observed).total_seconds()
                    if -1 <= age <= 30:
                        return normalize.quote(value)
                    # The server pushes every tick of a subscribed symbol, so an old price
                    # means a quiet market; RPC would return that same tick at a quota cost.
                    subscriptions: list[dict[str, Any]] = []
                    try:
                        subscriptions = stream.subscriptions(symbol) or []
                    except Exception:
                        subscriptions = []
                    if age > 30 and any(item.get("type") == "quotes" for item in subscriptions):
                        return normalize.quote(value)
        try:
            return normalize.quote(await self.read_rpc("get_symbol_price", symbol))
        except Exception as error:
            raise self.diagnose(error, "quote") from error

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        validate_timeframe(timeframe)
        if limit < 1:
            raise LonoraError("candle_limit_invalid")
        account = await self.resolve_account()
        try:
            async with asyncio.timeout(35):
                values = await account.get_historical_candles(
                    symbol=symbol, timeframe=timeframe, start_time=None, limit=min(limit, 1000)
                )
            if any(
                value.get("symbol", symbol) != symbol
                or value.get("timeframe", timeframe) != timeframe
                for value in values
            ):
                raise LonoraError("broker_candles_mismatch", 502)
            return [normalize.candle(value, symbol, timeframe) for value in values]
        except Exception as error:
            raise self.diagnose(error, "candles") from error

    async def history(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        try:
            response = await self.read_rpc(
                "get_deals_by_time_range", start, end, 0, min(limit, 1000)
            )
            fields = {
                "id",
                "orderId",
                "positionId",
                "symbol",
                "type",
                "entryType",
                "volume",
                "price",
                "profit",
                "commission",
                "swap",
                "clientId",
            }
            return [
                {
                    **{key: value for key, value in row.items() if key in fields},
                    "time": normalize.observed(row["time"]).isoformat(),
                }
                for row in response.get("deals", [])[:limit]
            ]
        except Exception as error:
            raise self.diagnose(error, "history") from error

    async def account(self) -> AccountState:
        try:
            payload = dict(await self.read_rpc("get_account_information"))
            entity = getattr(self, "account_instance", None)
            for field in ("login", "server"):
                if payload.get(field) is None and entity is not None:
                    try:
                        payload[field] = getattr(entity, field, None)
                    except (KeyError, AttributeError):
                        pass
            if payload.get("platform") is None and entity is not None:
                try:
                    version = getattr(entity, "version", None)
                    if version in {4, 5}:
                        payload["platform"] = "mt" + str(version)
                except (KeyError, AttributeError):
                    pass
            return normalize.account(
                payload,
                getattr(self, "connection_id", None) or self.account_id,
            )
        except Exception as error:
            raise self.diagnose(error, "account") from error

    async def positions(self) -> list[Position]:
        try:
            return [normalize.position(value) for value in await self.read_rpc("get_positions")]
        except Exception as error:
            raise self.diagnose(error, "positions") from error

    async def orders(self) -> list[Order]:
        try:
            return [normalize.order(value) for value in await self.read_rpc("get_orders")]
        except Exception as error:
            raise self.diagnose(error, "orders") from error

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        volume, price, sl, tp = (
            sdk_number(v)
            for v in (request.volume, request.price, request.stop_loss, request.take_profit)
        )
        if request.clear_stop_loss:
            sl = 0.0
        if request.clear_take_profit:
            tp = 0.0
        if request.action == "modify_order" and price is None:
            target = next(
                (
                    order
                    for order in await self.read_rpc("get_orders")
                    if str(order.get("id")) == request.order_id
                    and order.get("symbol") == request.symbol
                ),
                None,
            )
            if target is None:
                raise LonoraError("order_not_found", 404)
            price = sdk_number(Decimal(str(target["openPrice"])))
        # A read-only target lookup can replace a closed RPC wrapper. Take the
        # current ready wrapper immediately before recording the send boundary.
        rpc = await self.prepare()
        options = {"clientId": client_id(request.operation_id)}
        if before_send:
            await before_send()
        self.evidence = None
        try:
            creators = {
                "buy": "create_market_buy_order",
                "sell": "create_market_sell_order",
                "buy_limit": "create_limit_buy_order",
                "sell_limit": "create_limit_sell_order",
                "buy_stop": "create_stop_buy_order",
                "sell_stop": "create_stop_sell_order",
            }
            if request.action in creators:
                args = [request.symbol, volume] + (
                    [price] if request.action not in {"buy", "sell"} else []
                )
                response = await getattr(rpc, creators[request.action])(
                    *args, stop_loss=sl, take_profit=tp, options=options
                )
            elif request.action == "close_position":
                if volume is not None:
                    response = await rpc.close_position_partially(
                        request.position_id, volume, options=options
                    )
                else:
                    response = await rpc.close_position(request.position_id, options=options)
            elif request.action == "modify_position":
                response = await rpc.modify_position(
                    request.position_id, stop_loss=sl, take_profit=tp
                )
            elif request.action == "cancel_order":
                response = await rpc.cancel_order(request.order_id)
            else:
                response = await rpc.modify_order(
                    request.order_id, price, stop_loss=sl, take_profit=tp
                )
            from lonora_trading.retcodes import normalize_response

            status = normalize_response(response.get("stringCode"), response.get("numericCode"))
            return TradeResult(
                operation_id=request.operation_id,
                status=status,
                broker_id=str(
                    response.get("orderId")
                    or response.get("positionId")
                    or (request.order_id or request.position_id if status == "confirmed" else None)
                    or ""
                )
                or None,
                code=str(response.get("stringCode") or ""),
                details={
                    "partial_execution": response.get("stringCode") == "TRADE_RETCODE_DONE_PARTIAL"
                    or response.get("numericCode") == 10010,
                    "numeric_code": response.get("numericCode"),
                    "order_id": response.get("orderId"),
                    "position_id": response.get("positionId"),
                    "deal_id": response.get("dealId"),
                    "price": response.get("price"),
                    "description": safe_exception_message(
                        Exception(
                            str(response.get("message") or response.get("description") or "")
                        ),
                        getattr(self, "_log_redactions", ()),
                    )
                    or None,
                },
            )
        except Exception as error:
            if closed_error(error) or is_closed(rpc):
                await self.invalidate("rpc", rpc)
            self.diagnose(error, "trade")
            from lonora_trading.retcodes import normalize_response

            # The official SDK raises TradeException on a received broker rejection.
            # A validation error rejects the request itself, so no order exists to reconcile.
            # Transport/timeouts and contradictory codes remain uncertain.
            validation_exception: Any = importlib.import_module(
                "metaapi_cloud_sdk.clients.error_handler"
            ).ValidationException
            if isinstance(error, validation_exception):
                return TradeResult(
                    operation_id=request.operation_id,
                    status="failed",
                    code="broker_request_rejected",
                    details={
                        "description": safe_exception_message(
                            error, getattr(self, "_log_redactions", ())
                        )
                    },
                )
            trade_exception: Any = importlib.import_module(
                "metaapi_cloud_sdk.clients.metaapi.trade_exception"
            ).TradeException
            if isinstance(error, trade_exception):
                string_code = getattr(error, "stringCode", None)
                numeric_code = getattr(error, "numericCode", None)
                status = normalize_response(string_code, numeric_code)
                if status == "failed":
                    return TradeResult(
                        operation_id=request.operation_id,
                        status="failed",
                        code=string_code,
                        details={
                            "numeric_code": numeric_code,
                            "description": safe_exception_message(
                                error, getattr(self, "_log_redactions", ())
                            ),
                        },
                    )
            return TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )

    async def reconciliation_evidence(
        self,
        submitted_at: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        # A broad, synchronized read can serve all subsequent requests inside
        # its history window. Older journal operations must not age out after7d.
        end = datetime.now(UTC)
        if submitted_at is not None and submitted_at.tzinfo is None:
            raise LonoraError("broker_reconciliation_time_invalid", 409)
        since = min(end - timedelta(days=7), submitted_at or end)
        start = since.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        start -= timedelta(minutes=5)
        lock = self.__dict__.setdefault("evidence_lock", asyncio.Lock())
        async with lock:
            now = asyncio.get_running_loop().time()
            cached = getattr(self, "evidence", None)
            if (
                cached is not None
                and len(cached) == 5
                and now - cached[0] < EVIDENCE_SECONDS
                and cached[1] <= start
            ):
                return cached[2], cached[3], cached[4]
            current = [*await self.read_rpc("get_positions"), *await self.read_rpc("get_orders")]
            collected: list[list[dict[str, Any]]] = []
            for method, key in (
                ("get_deals_by_time_range", "deals"),
                ("get_history_orders_by_time_range", "historyOrders"),
            ):
                values: list[dict[str, Any]] = []
                for offset in range(0, 10000, 1000):
                    response = await self.read_rpc(method, start, end, offset, 1000)
                    if response.get("synchronizing"):
                        raise LonoraError("broker_history_synchronizing", 409)
                    page = response.get(key, [])
                    if not isinstance(page, list):
                        raise LonoraError("broker_history_invalid", 502)
                    if any(not isinstance(item, dict) for item in cast(list[Any], page)):
                        raise LonoraError("broker_history_invalid", 502)
                    values.extend(cast(list[dict[str, Any]], page))
                    if len(cast(list[Any], page)) < 1000:
                        break
                else:
                    # Keep uncertainty explicit instead of treating truncated
                    # history as proof of an absent financial operation.
                    raise LonoraError("broker_history_limit", 409)
                collected.append(values)
            deals, orders = collected
            self.evidence = (now, start, current, deals, orders)
            return current, deals, orders

    async def reconcile(
        self,
        operation_id: str,
        request: TradeRequest | None = None,
        *,
        submitted_at: datetime | None = None,
    ) -> TradeResult:
        if request and request.action in {"modify_order", "modify_position", "cancel_order"}:
            return TradeResult(
                operation_id=operation_id, status="ambiguous", code="mutation_evidence_required"
            )
        target = client_id(operation_id)
        try:
            current, deals, orders = await self.reconciliation_evidence(submitted_at)
            items = (
                deals
                if request and request.action == "close_position"
                else current + deals + orders
            )
            matches: list[dict[str, Any]] = []
            for item in items:
                # MetaApi may retain the entry clientId on an exit deal; the
                # exit's own correlation is then in brokerComment, with ':' suffix.
                comment = item.get("brokerComment") or item.get("comment")
                tagged = item.get("clientId") == target or comment in {target, target + ":"}
                if not tagged or not item.get("id"):
                    continue
                if request and item.get("symbol") != request.symbol:
                    continue
                if (
                    request
                    and request.action == "close_position"
                    and (
                        str(item.get("positionId")) != request.position_id
                        or item.get("entryType")
                        not in {"DEAL_ENTRY_OUT", "DEAL_ENTRY_OUT_BY", "DEAL_ENTRY_INOUT"}
                    )
                ):
                    continue
                if (
                    request
                    and request.action in {"buy", "sell"}
                    and item in orders
                    and item.get("state")
                    not in {"ORDER_STATE_FILLED", "ORDER_STATE_PARTIAL", "ORDER_STATE_REJECTED"}
                ):
                    continue
                matches.append(item)
            if matches:
                found = matches[0]
                rejected = found.get("state") == "ORDER_STATE_REJECTED"
                return TradeResult(
                    operation_id=operation_id,
                    status="failed" if rejected else "confirmed",
                    broker_id=str(found["id"]),
                    code="broker_order_rejected" if rejected else None,
                    details={
                        "reconciled": True,
                        "order_id": found.get("orderId"),
                        "position_id": found.get("positionId"),
                        "deal_id": found.get("id") if found in deals else None,
                        "broker_state": found.get("state"),
                        "price": found.get("price", found.get("openPrice")),
                        "volume": found.get("volume"),
                    },
                )
            return TradeResult(
                operation_id=operation_id, status="ambiguous", code="execution_not_observed"
            )
        except Exception as error:
            raise self.diagnose(error, "reconciliation") from error

    async def close(self) -> None:
        self._closing = True
        for kind in ("streaming", "rpc"):
            slot = self._slot(kind)
            if slot.task is not None and not slot.task.done():
                slot.task.cancel()
                await asyncio.gather(slot.task, return_exceptions=True)
            connection = getattr(self, "streaming" if kind == "streaming" else "rpc", None)
            if connection is not None:
                await self.invalidate(kind, connection)
        websocket = getattr(self.api, "_metaapi_websocket_client", None)
        domain = getattr(websocket, "_domain_client", None)
        discovery = getattr(domain, "_lonora_domain_slot", None)
        if discovery is not None and discovery.task is not None and not discovery.task.done():
            discovery.task.cancel()
            await asyncio.gather(discovery.task, return_exceptions=True)
        self.api.close()
