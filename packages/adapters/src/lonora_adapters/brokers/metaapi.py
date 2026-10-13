import asyncio
import hashlib
import importlib
import os
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

import httpx
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError

from . import normalize


def sdk_number(value: Decimal | None) -> float | None:
    if value is None:
        return None
    converted = float(value)
    if not value.is_finite() or Decimal(str(converted)) != value:
        raise LonoraError("broker_numeric_precision_loss")
    return converted


def client_id(operation_id: str) -> str:
    return "LN_" + hashlib.sha256(operation_id.encode()).hexdigest()[:24]


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
    def __init__(self, account_id: str, region: str | None, token: str):
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
        self.account_instance: Any = None
        self.rpc: Any = None
        self.lock = asyncio.Lock()

    async def prepare(self) -> Any:
        async with self.lock:
            try:
                if self.account_instance is None:
                    self.account_instance = await self.api.metatrader_account_api.get_account(
                        self.account_id
                    )
                if self.rpc is None:
                    self.rpc = self.account_instance.get_rpc_connection()
                    await self.rpc.connect()
                await self.rpc.wait_synchronized(timeout_in_seconds=20)
                return self.rpc
            except Exception:
                raise LonoraError("broker_connection_unavailable", 502) from None

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

    async def quote(self, symbol: str) -> Quote:
        rpc = await self.prepare()
        try:
            return normalize.quote(await rpc.get_symbol_price(symbol))
        except Exception:
            raise LonoraError("broker_quote_unavailable", 502) from None

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        await self.prepare()
        try:
            values = await self.account_instance.get_historical_candles(
                symbol, timeframe, None, min(limit, 1000)
            )
            return [normalize.candle(value, symbol, timeframe) for value in values]
        except Exception:
            raise LonoraError("broker_candles_unavailable", 502) from None

    async def account(self) -> AccountState:
        rpc = await self.prepare()
        try:
            return normalize.account(await rpc.get_account_information(), self.account_id)
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
        if before_send:
            await before_send()
        volume, price, sl, tp = (
            sdk_number(v)
            for v in (request.volume, request.price, request.stop_loss, request.take_profit)
        )
        options = {"clientId": client_id(request.operation_id)}
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
                response = await rpc.close_position(request.position_id, options=options)
            elif request.action == "modify_position":
                response = await rpc.modify_position(
                    request.position_id, stop_loss=sl, take_profit=tp
                )
            elif request.action == "cancel_order":
                response = await rpc.cancel_order(request.order_id)
            else:
                response = await rpc.modify_order(
                    request.order_id, price, stop_loss=sl, take_profit=tp, options=options
                )
            from lonora_trading.retcodes import normalize_retcode

            status = normalize_retcode(response.get("stringCode", response.get("numericCode")))
            return TradeResult(
                operation_id=request.operation_id,
                status=status,
                broker_id=str(response.get("orderId") or response.get("positionId") or "") or None,
                code=str(response.get("stringCode") or ""),
                details={"numeric_code": response.get("numericCode")},
            )
        except Exception:
            return TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )

    async def reconcile(
        self, operation_id: str, request: TradeRequest | None = None
    ) -> TradeResult:
        rpc = await self.prepare()
        target = client_id(operation_id)
        try:
            current = [*await rpc.get_positions(), *await rpc.get_orders()]
            history = await rpc.get_deals_by_time_range(
                datetime.now(UTC) - timedelta(days=7), datetime.now(UTC), 0, 1000
            )
            items = current + list(history.get("deals", []))
            matches = [item for item in items if item.get("clientId") == target]
            if matches:
                return TradeResult(
                    operation_id=operation_id,
                    status="confirmed",
                    broker_id=str(matches[0].get("id") or ""),
                    details={"reconciled": True},
                )
            return TradeResult(
                operation_id=operation_id, status="ambiguous", code="execution_not_observed"
            )
        except Exception:
            raise LonoraError("broker_reconciliation_unavailable", 502) from None

    async def close(self) -> None:
        if self.rpc is not None:
            await self.rpc.close()
        self.api.close()
