import asyncio
import importlib
import logging
import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
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

log = logging.getLogger("lonora.metaapi")


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
        return LonoraError("broker_candles_request_rejected", 422)
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


def configure_sdk_transport() -> None:
    """Keep official SDK domain discovery and route its transports through inherited proxies."""
    aiohttp: Any = importlib.import_module("aiohttp")
    socketio: Any = importlib.import_module("socketio")
    http_module: Any = importlib.import_module("metaapi_cloud_sdk.clients.http_client")
    websocket_module: Any = importlib.import_module(
        "metaapi_cloud_sdk.clients.metaapi.metaapi_websocket_client"
    )
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
        def __init__(self, *args: Any, **kwargs: Any):
            session = aiohttp.ClientSession(trust_env=True)
            original_connect = session.ws_connect

            def connect(url: str, **options: Any) -> Any:
                validate_sdk_url(str(url))
                proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
                if proxy:
                    options["proxy"] = proxy
                return original_connect(url, **options)

            session.ws_connect = connect
            socketio.AsyncClient.__init__(self, *args, http_session=session, **kwargs)

        async def connect(self, url: str, *args: Any, **kwargs: Any) -> Any:
            validate_sdk_url(url)
            return await socketio.AsyncClient.connect(self, url, *args, **kwargs)

    http_module.HttpClient._make_request = request
    websocket_module.socketio = SimpleNamespace(AsyncClient=ProxySocketClient)
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

    def diagnose(self, error: Exception, stage: str) -> LonoraError:
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
                    self.account_instance = await self.api.metatrader_account_api.get_account(
                        self.account_id
                    )
                except Exception as error:
                    raise self.diagnose(error, "account") from error
            return self.account_instance

    async def prepare(self) -> Any:
        account = await self.resolve_account()
        async with self.lock:
            try:
                if self.rpc is None:
                    self.rpc = account.get_rpc_connection()
                    await self.rpc.connect()
                await self.rpc.wait_synchronized(timeout_in_seconds=20)
                return self.rpc
            except Exception as error:
                raise self.diagnose(error, "rpc") from error

    async def symbols(self) -> list[str]:
        rpc = await self.prepare()
        try:
            return sorted(await rpc.get_symbols())
        except Exception:
            raise LonoraError("broker_symbols_unavailable", 502) from None

    async def instrument(self, symbol: str) -> Instrument:
        rpc = await self.prepare()
        try:
            result = normalize.instrument(await rpc.get_symbol_specification(symbol))
            if result.symbol != symbol:
                raise ValueError("broker_symbol_mismatch")
            return result
        except Exception:
            raise LonoraError("broker_instrument_unavailable", 502) from None

    async def instruments(self) -> list[Instrument]:
        rpc = await self.prepare()
        try:
            symbols = await rpc.get_symbols()
            if len(symbols) > 2000:
                symbols = symbols[:2000]
            result: list[Instrument] = []
            semaphore = asyncio.Semaphore(8)

            async def read(symbol: str) -> None:
                async with semaphore:
                    value = await rpc.get_symbol_specification(symbol)
                    result.append(normalize.instrument(value))

            await asyncio.gather(*(read(symbol) for symbol in symbols))
            return sorted(result, key=lambda instrument: instrument.symbol)
        except Exception:
            raise LonoraError("broker_instruments_unavailable", 502) from None

    async def stream_quotes(self, symbol: str) -> AsyncGenerator[Quote, None]:
        # SDK streaming is shared by symbol listeners and survives without a browser.
        await self.prepare()
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
        async with self.stream_lock:
            if self.streaming is None:
                self.streaming = self.account_instance.get_streaming_connection()
                await self.streaming.connect()
            stream = self.streaming
            stream.add_synchronization_listener(listener)
        try:
            await stream.wait_synchronized({"timeoutInSeconds": 30})
            await stream.subscribe_to_market_data(symbol, [{"type": "quotes"}])
            yield await self.quote(symbol)
            while True:
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=30)
                except TimeoutError:
                    # Verify synchronization and resubscribe after SDK reconnects. A fresh
                    # RPC observation provides recovery; never synthesize price/timestamps.
                    await stream.wait_synchronized({"timeoutInSeconds": 20})
                    await stream.subscribe_to_market_data(symbol, [{"type": "quotes"}])
                    yield await self.quote(symbol)
        except asyncio.CancelledError:
            raise
        except Exception:
            raise LonoraError("broker_stream_unavailable", 502) from None
        finally:
            stream.remove_synchronization_listener(listener)
            # This generator is the sole resident consumer of this exact symbol.
            try:
                await stream.unsubscribe_from_market_data(symbol, [{"type": "quotes"}])
            except Exception:
                pass

    async def stream_candles(self, symbol: str, timeframe: str) -> AsyncGenerator[Candle, None]:
        validate_timeframe(timeframe)
        account = await self.resolve_account()
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
        async with self.stream_lock:
            if self.streaming is None:
                self.streaming = account.get_streaming_connection()
                await self.streaming.connect()
            stream = self.streaming
            stream.add_synchronization_listener(listener)
        try:
            await stream.wait_synchronized({"timeoutInSeconds": 30})
            await stream.subscribe_to_market_data(symbol, subscription)
            while True:
                try:
                    candle = await asyncio.wait_for(queue.get(), timeout=30)
                    if isinstance(candle, LonoraError):
                        raise candle
                    yield candle
                except TimeoutError:
                    await stream.wait_synchronized({"timeoutInSeconds": 20})
                    await stream.subscribe_to_market_data(symbol, subscription)
                    # Recovery is exact broker history, never OHLC inferred from quotes.
                    for candle in await self.candles(symbol, timeframe, 2):
                        yield candle
        except asyncio.CancelledError:
            raise
        except Exception as error:
            raise self.diagnose(error, "candles") from error
        finally:
            stream.remove_synchronization_listener(listener)
            try:
                await stream.unsubscribe_from_market_data(symbol, subscription)
            except Exception:
                pass

    async def quote(self, symbol: str) -> Quote:
        rpc = await self.prepare()
        try:
            return normalize.quote(await rpc.get_symbol_price(symbol))
        except Exception:
            raise LonoraError("broker_quote_unavailable", 502) from None

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        validate_timeframe(timeframe)
        if limit < 1:
            raise LonoraError("candle_limit_invalid")
        account = await self.resolve_account()
        try:
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
        rpc = await self.prepare()
        try:
            response = await rpc.get_deals_by_time_range(start, end, 0, min(limit, 1000))
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
        except Exception:
            raise LonoraError("broker_history_unavailable", 502) from None

    async def account(self) -> AccountState:
        rpc = await self.prepare()
        try:
            payload = dict(await rpc.get_account_information())
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
        except Exception:
            raise LonoraError("broker_account_unavailable", 502) from None

    async def positions(self) -> list[Position]:
        rpc = await self.prepare()
        try:
            return [normalize.position(value) for value in await rpc.get_positions()]
        except Exception:
            raise LonoraError("broker_positions_unavailable", 502) from None

    async def orders(self) -> list[Order]:
        rpc = await self.prepare()
        try:
            return [normalize.order(value) for value in await rpc.get_orders()]
        except Exception:
            raise LonoraError("broker_orders_unavailable", 502) from None

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        rpc = await self.prepare()
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
                    for order in await rpc.get_orders()
                    if str(order.get("id")) == request.order_id
                    and order.get("symbol") == request.symbol
                ),
                None,
            )
            if target is None:
                raise LonoraError("order_not_found", 404)
            price = sdk_number(Decimal(str(target["openPrice"])))
        options = {"clientId": client_id(request.operation_id)}
        if before_send:
            await before_send()
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
                },
            )
        except Exception as error:
            from lonora_trading.retcodes import normalize_response

            # The official SDK raises TradeException on a received broker rejection.
            # Transport/timeouts and contradictory codes remain uncertain.
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
                        details={"numeric_code": numeric_code},
                    )
            return TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )

    async def reconcile(
        self, operation_id: str, request: TradeRequest | None = None
    ) -> TradeResult:
        # Modification/cancellation evidence cannot be inferred merely from an order
        # or position carrying an old clientId. Keep uncertainty blocked conservatively.
        if request and request.action in {"modify_order", "modify_position", "cancel_order"}:
            return TradeResult(
                operation_id=operation_id, status="ambiguous", code="mutation_evidence_required"
            )
        rpc = await self.prepare()
        target = client_id(operation_id)
        try:
            current = [*await rpc.get_positions(), *await rpc.get_orders()]
            history = await rpc.get_deals_by_time_range(
                datetime.now(UTC) - timedelta(days=7), datetime.now(UTC), 0, 1000
            )
            deals = list(history.get("deals", []))
            items = deals if request and request.action == "close_position" else current + deals
            matches = [item for item in items if item.get("clientId") == target]
            if matches:
                return TradeResult(
                    operation_id=operation_id,
                    status="confirmed",
                    broker_id=str(matches[0].get("id") or ""),
                    details={
                        "reconciled": True,
                        "order_id": matches[0].get("orderId"),
                        "position_id": matches[0].get("positionId"),
                        "deal_id": matches[0].get("id") if matches[0] in deals else None,
                    },
                )
            return TradeResult(
                operation_id=operation_id, status="ambiguous", code="execution_not_observed"
            )
        except Exception:
            raise LonoraError("broker_reconciliation_unavailable", 502) from None

    async def close(self) -> None:
        if self.streaming is not None:
            await self.streaming.close()
            self.streaming = None
        if self.rpc is not None:
            await self.rpc.close()
        self.api.close()
