"""Alpaca paper-trading adapter behind the single executor.

Paper only: the trading host is fixed to ``paper-api.alpaca.markets`` and market data to
``data.alpaca.markets``. Nothing in a connection's configuration can point this adapter at
the live trading host; live trading is a later owner decision.

Every mutation is one HTTP request sent after the executor's ``before_send`` callback
returns. All lookups the mutation needs (instrument class, market clock, protection legs,
the pending order) happen before that boundary, so a refusal there is provably not sent.
The API keys are held only by the HTTP client's headers; they never reach a result, a
diagnostic or a log line.
"""

import asyncio
import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from time import monotonic
from typing import Any, cast

import httpx
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.chart_controller import validate_timeframe
from lonora_core.error_logging import safe_exception_message
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import broker_operation_tag
from pydantic import ValidationError

from . import alpaca_normalize as normalize

log = logging.getLogger("lonora.alpaca")

TRADING_HOST = "paper-api.alpaca.markets"
DATA_HOST = "data.alpaca.markets"
TRADING_URL = "https://" + TRADING_HOST
DATA_URL = "https://" + DATA_HOST
STOCK_FEED = "iex"  # The feed every Alpaca account can read without a data subscription.
ASSET_CACHE_SECONDS = 600
QUOTE_POLL_SECONDS = 2.0
CANDLE_POLL_SECONDS = 10.0
REQUEST_TIMEOUT_SECONDS = 20.0
# A cancelled order releases its quantity, and a market close fills, asynchronously.
POLL_SECONDS = 0.5
POLLS = 20

# Test seam only: an in-process fake Alpaca server. Configuration cannot reach it, and the
# URLs stay the fixed paper hosts whatever transport carries them.
transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None


def client_order_id(operation_id: str) -> str:
    """The executor's operation identity as Alpaca's ``client_order_id``."""
    return broker_operation_tag(operation_id)


def credentials_secret(key_id: str, secret_key: str) -> str:
    """Both keys travel and rest together, encrypted, as one stored secret."""
    key_id, secret_key = key_id.strip(), secret_key.strip()
    if not key_id or not secret_key:
        raise LonoraError("broker_secret_required", 409)
    return json.dumps({"key_id": key_id, "secret_key": secret_key})


def credentials_from_secret(value: str) -> tuple[str, str]:
    try:
        payload = json.loads(value)
    except ValueError as error:
        raise LonoraError("broker_secret_invalid", 409) from error
    if not isinstance(payload, dict):
        raise LonoraError("broker_secret_invalid", 409)
    data = cast(dict[str, Any], payload)
    key_id, secret_key = data.get("key_id"), data.get("secret_key")
    if (
        not isinstance(key_id, str)
        or not isinstance(secret_key, str)
        or not key_id
        or not secret_key
    ):
        raise LonoraError("broker_secret_invalid", 409)
    return key_id, secret_key


class AlpacaHTTPError(Exception):
    """A received Alpaca error response: the request was answered, not lost."""

    def __init__(self, status_code: int, code: Any, message: str):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.code = code
        self.message = message


def provider_error(error: Exception, stage: str) -> LonoraError:
    """Read-side broker errors in the existing taxonomy (the MetaApi adapter's codes)."""
    if isinstance(error, LonoraError):
        return error
    candles = stage == "candles"
    if isinstance(error, AlpacaHTTPError):
        status = error.status_code
        if status in {401, 403}:
            return LonoraError("broker_credentials_rejected", 409)
        if status == 404:
            if stage in {"quote", "instrument", "candles"}:
                return LonoraError("symbol_not_found", 404)
            return LonoraError("broker_account_not_found", 404)
        if status == 429:
            return LonoraError("broker_rate_limited", 429)
        if status in {400, 422}:
            return LonoraError(
                "broker_candles_request_rejected" if candles else "broker_request_rejected", 422
            )
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return LonoraError(
            "broker_candles_timeout" if candles else "broker_connection_timeout", 504
        )
    if isinstance(error, (ValidationError, ValueError, KeyError, TypeError)):
        return LonoraError("broker_candles_invalid" if candles else "broker_response_invalid", 502)
    return LonoraError(
        "broker_candles_unavailable" if candles else "broker_connection_unavailable", 502
    )


def rejection_code(error: AlpacaHTTPError, request: TradeRequest) -> str:
    """A received refusal of a mutation, in the existing financial result codes.

    Alpaca answers 403 for buying power, held quantity and shorting refusals and 422 for
    invalid orders; the broker's own code and message stay in the result details.
    """
    if error.status_code == 401:
        return "broker_credentials_rejected"
    if error.status_code == 404:
        return "position_not_found" if request.action == "close_position" else "order_not_found"
    if error.status_code == 429:
        return "broker_rate_limited"
    return "broker_request_rejected"


def decimal_text(value: Decimal) -> str:
    if not value.is_finite():
        raise LonoraError("broker_numeric_precision_loss")
    return format(value, "f")


@dataclass
class Plan:
    """The mutation a request sends, decided before the send boundary."""

    method: str
    path: str
    body: dict[str, Any] | None
    position: Position | None = None
    groups: list[normalize.ProtectionGroup] = field(default_factory=list[normalize.ProtectionGroup])


INTACT = {"new", "accepted", "held", "partially_filled"}


class AlpacaBroker:
    environment = "paper"

    def __init__(self, key_id: str, secret_key: str, connection_id: str | None = None):
        if not key_id or not secret_key:
            raise LonoraError("broker_secret_required", 409)
        self.connection_id = connection_id
        self._log_redactions = (key_id, secret_key)
        self.client = httpx.AsyncClient(
            headers={"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret_key},
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
            trust_env=True,
            transport=transport_factory() if transport_factory is not None else None,
        )
        self.closed = False
        self._assets: dict[str, dict[str, Any]] = {}
        self._assets_by_id: dict[str, dict[str, Any]] = {}
        self._compact: dict[str, str] = {}
        self._assets_at = 0.0
        self._assets_lock = asyncio.Lock()
        self._currency: str | None = None

    # -- transport -------------------------------------------------------------------

    def diagnose(self, error: Exception, stage: str) -> LonoraError:
        if isinstance(error, LonoraError) and error.diagnostic_message:
            return error
        failure = provider_error(error, stage)
        failure.diagnostic_type = type(error).__name__
        failure.diagnostic_message = safe_exception_message(error, self._log_redactions)
        log.warning(
            "broker_%s_failed code=%s type=%s message=%s",
            stage,
            failure.code,
            type(error).__name__,
            failure.diagnostic_message,
        )
        return failure

    async def request(
        self,
        method: str,
        base: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> Any:
        if self.closed:
            raise LonoraError("broker_connection_closed", 503)
        if base not in {TRADING_URL, DATA_URL}:
            raise LonoraError("broker_endpoint_forbidden", 403)
        response = await self.client.request(method, base + path, params=params, json=body)
        if response.status_code >= 400:
            code: Any = None
            message = response.reason_phrase
            try:
                payload = response.json()
                if isinstance(payload, dict):
                    data = cast(dict[str, Any], payload)
                    code, message = data.get("code"), str(data.get("message") or message)
            except ValueError:
                pass
            raise AlpacaHTTPError(response.status_code, code, message)
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    async def trading(self, method: str, path: str, **options: Any) -> Any:
        return await self.request(method, TRADING_URL, path, **options)

    async def data(self, path: str, params: dict[str, Any]) -> Any:
        return await self.request("GET", DATA_URL, path, params=params)

    # -- catalog ---------------------------------------------------------------------

    async def assets(self) -> dict[str, dict[str, Any]]:
        async with self._assets_lock:
            if not self._assets or monotonic() - self._assets_at >= ASSET_CACHE_SECONDS:
                rows: list[dict[str, Any]] = []
                for asset_class in ("us_equity", "crypto"):
                    values = await self.trading(
                        "GET", "/v2/assets", params={"status": "active", "asset_class": asset_class}
                    )
                    if not isinstance(values, list):
                        raise ValueError("broker_assets_invalid")
                    rows.extend(
                        cast(dict[str, Any], item)
                        for item in cast(list[Any], values)
                        if isinstance(item, dict) and cast(dict[str, Any], item).get("tradable")
                    )
                self._assets = {str(row["symbol"]): row for row in rows}
                self._assets_by_id = {str(row["id"]): row for row in rows if row.get("id")}
                self._compact = {
                    str(row["symbol"]).replace("/", ""): str(row["symbol"])
                    for row in rows
                    if normalize.is_crypto(row)
                }
                self._assets_at = monotonic()
            return self._assets

    async def asset(self, symbol: str) -> dict[str, Any]:
        asset = (await self.assets()).get(symbol)
        if asset is None:
            raise LonoraError("symbol_not_found", 404)
        return asset

    def canonical(self, value: dict[str, Any]) -> str:
        """Alpaca spells crypto ``BTC/USD`` in its catalog and ``BTCUSD`` on positions."""
        asset = self._assets_by_id.get(str(value.get("asset_id") or ""))
        if asset is not None:
            return str(asset["symbol"])
        symbol = str(value["symbol"])
        return self._compact.get(symbol, symbol)

    async def account_currency(self) -> str:
        if self._currency is None:
            self._currency = str(
                (await self.trading("GET", "/v2/account")).get("currency") or "USD"
            )
        return self._currency

    async def symbols(self) -> list[str]:
        try:
            return sorted(await self.assets())
        except Exception as error:
            raise self.diagnose(error, "symbols") from error

    async def instruments(self) -> list[Instrument]:
        try:
            return sorted(
                (normalize.instrument(asset) for asset in (await self.assets()).values()),
                key=lambda item: item.symbol,
            )
        except Exception as error:
            raise self.diagnose(error, "instruments") from error

    async def instrument(self, symbol: str) -> Instrument:
        try:
            return normalize.instrument(await self.asset(symbol))
        except Exception as error:
            raise self.diagnose(error, "instrument") from error

    # -- market data -----------------------------------------------------------------

    async def quote(self, symbol: str) -> Quote:
        try:
            asset = await self.asset(symbol)
            crypto = normalize.is_crypto(asset)
            path = "/v1beta3/crypto/us/latest/quotes" if crypto else "/v2/stocks/quotes/latest"
            params = {"symbols": symbol, **({} if crypto else {"feed": STOCK_FEED})}
            payload = await self.data(path, params)
            value = normalize.mapping(normalize.mapping(payload).get("quotes")).get(symbol)
            if not value:
                raise LonoraError("quote_unavailable", 404)
            return normalize.quote(
                normalize.mapping(value),
                symbol,
                normalize.instrument(asset),
                account_currency=await self.account_currency(),
            )
        except Exception as error:
            raise self.diagnose(error, "quote") from error

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        validate_timeframe(timeframe)
        if limit < 1:
            raise LonoraError("candle_limit_invalid")
        limit = min(limit, 1000)
        try:
            asset = await self.asset(symbol)
            crypto = normalize.is_crypto(asset)
            frame, seconds = normalize.TIMEFRAMES[timeframe]
            # Without a start Alpaca begins at today's open. Look back far enough for
            # `limit` bars across closed sessions, newest first, then restore order.
            lookback = max(timedelta(seconds=seconds * limit * 3), timedelta(days=7))
            params: dict[str, Any] = {
                "symbols": symbol,
                "timeframe": frame,
                "limit": limit,
                "sort": "desc",
                "start": (datetime.now(UTC) - lookback).isoformat().replace("+00:00", "Z"),
                **({} if crypto else {"feed": STOCK_FEED, "adjustment": "raw"}),
            }
            path = "/v1beta3/crypto/us/bars" if crypto else "/v2/stocks/bars"
            payload = await self.data(path, params)
            values: Any = normalize.mapping(normalize.mapping(payload).get("bars")).get(symbol)
            if values is None:
                values = []
            if not isinstance(values, list):
                raise LonoraError("broker_candles_invalid", 502)
            rows = [
                normalize.candle(normalize.mapping(value), symbol, timeframe)
                for value in cast(list[Any], values)[:limit]
            ]
            return sorted(rows, key=lambda item: item.time)
        except Exception as error:
            raise self.diagnose(error, "candles") from error

    async def stream_quotes(self, symbol: str) -> AsyncGenerator[Quote, None]:
        # REST polling: only quotes Alpaca reported, never interpolated.
        previous: Quote | None = None
        while not self.closed:
            value = await self.quote(symbol)
            if value != previous:
                previous = value
                yield value
            await asyncio.sleep(QUOTE_POLL_SECONDS)

    async def stream_candles(self, symbol: str, timeframe: str) -> AsyncGenerator[Candle, None]:
        validate_timeframe(timeframe)
        seen: dict[datetime, Candle] = {}
        while not self.closed:
            # Exact broker bars, including a correction of the forming bar.
            for value in await self.candles(symbol, timeframe, 2):
                if seen.get(value.time) != value:
                    seen[value.time] = value
                    yield value
            await asyncio.sleep(CANDLE_POLL_SECONDS)

    # -- account state ---------------------------------------------------------------

    async def metadata_identity(self) -> dict[str, Any]:
        """Read-only identity for connection verification; never places an order."""
        try:
            payload = await self.trading("GET", "/v2/account")
            return normalize.identity(payload)
        except Exception as error:
            raise self.diagnose(error, "account") from error

    async def account(self) -> AccountState:
        try:
            payload = await self.trading("GET", "/v2/account")
            self._currency = str(payload.get("currency") or "USD")
            return normalize.account(payload, self.connection_id or str(payload["id"]))
        except Exception as error:
            raise self.diagnose(error, "account") from error

    async def open_orders(self) -> list[dict[str, Any]]:
        values = await self.trading(
            "GET", "/v2/orders", params={"status": "open", "limit": 500, "nested": "false"}
        )
        if not isinstance(values, list):
            raise ValueError("broker_orders_invalid")
        if len(cast(list[Any], values)) >= 500:
            # A truncated book would hide exposure or protection.
            raise LonoraError("broker_snapshot_limit", 409)
        return [cast(dict[str, Any], item) for item in cast(list[Any], values)]

    async def book(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        await self.assets()
        positions, orders = await asyncio.gather(
            self.trading("GET", "/v2/positions"), self.open_orders()
        )
        if not isinstance(positions, list):
            raise ValueError("broker_positions_invalid")
        return [cast(dict[str, Any], item) for item in cast(list[Any], positions)], orders

    async def positions(self) -> list[Position]:
        try:
            positions, orders = await self.book()
            return normalize.positions(positions, orders, self.canonical)
        except Exception as error:
            raise self.diagnose(error, "positions") from error

    async def orders(self) -> list[Order]:
        try:
            _, orders = await self.book()
            entries = normalize.entry_orders(orders)
            references: dict[str, Decimal] = {}
            for value in entries:
                if value.get("type") == "market":
                    # A queued market order has no price. Its exposure is valued at the
                    # side it would take now, never at zero.
                    symbol = self.canonical(value)
                    if symbol not in references:
                        price = await self.quote(symbol)
                        references[symbol] = price.ask if value.get("side") == "buy" else price.bid
            return normalize.orders(orders, self.canonical, references)
        except Exception as error:
            raise self.diagnose(error, "orders") from error

    async def history(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        try:
            await self.assets()
            rows: list[dict[str, Any]] = []
            token: str | None = None
            while len(rows) < min(limit, 1000):
                params: dict[str, Any] = {
                    "after": start.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "until": end.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                    "direction": "desc",
                    "page_size": 100,
                    **({"page_token": token} if token else {}),
                }
                page = await self.trading("GET", "/v2/account/activities/FILL", params=params)
                if not isinstance(page, list) or not page:
                    break
                items = [cast(dict[str, Any], item) for item in cast(list[Any], page)]
                rows.extend(normalize.fill(item, self.canonical) for item in items)
                if len(items) < 100:
                    break
                token = str(items[-1]["id"])
            return rows[:limit]
        except Exception as error:
            raise self.diagnose(error, "history") from error

    # -- execution -------------------------------------------------------------------

    async def market_open(self) -> bool:
        clock = await self.trading("GET", "/v2/clock")
        return bool(clock.get("is_open"))

    async def prepare(self, request: TradeRequest) -> Plan:
        """Everything the mutation needs, read before the send boundary.

        Returns the HTTP mutation to send, and for a close of a protected position the
        protection that must be released first. Every refusal here raises before
        ``before_send``, so the executor records it as never sent.
        """
        asset = await self.asset(request.symbol)
        crypto = normalize.is_crypto(asset)
        tag = client_order_id(request.operation_id)
        entry = request.action in normalize.ENTRY_ACTIONS
        if request.action in {"buy", "sell", "close_position"} and not crypto:
            # A stock market order outside the session would queue at an unknown price;
            # refuse it now, as a MetaTrader server refuses with market closed.
            if not await self.market_open():
                raise LonoraError("market_closed", 409)
        if entry:
            if request.volume is None:
                raise LonoraError("volume_required", 422)
            kind = normalize.ENTRY_ACTIONS[request.action]
            if crypto and kind == "stop":
                raise LonoraError("broker_order_type_unsupported", 422)
            protected = request.stop_loss is not None or request.take_profit is not None
            if crypto and protected:
                # Alpaca offers no bracket or OTO orders for crypto.
                raise LonoraError("broker_protection_unsupported", 422)
            body: dict[str, Any] = {
                "symbol": request.symbol,
                "qty": decimal_text(request.volume),
                "side": "buy" if request.action.startswith("buy") else "sell",
                "type": kind,
                "time_in_force": "gtc" if crypto or kind != "market" else "day",
                "client_order_id": tag,
            }
            if kind != "market":
                if request.price is None:
                    raise LonoraError("price_required", 422)
                body["limit_price" if kind == "limit" else "stop_price"] = decimal_text(
                    request.price
                )
            if protected:
                body["order_class"] = (
                    "bracket"
                    if request.stop_loss is not None and request.take_profit is not None
                    else "oto"
                )
                if request.take_profit is not None:
                    body["take_profit"] = {"limit_price": decimal_text(request.take_profit)}
                if request.stop_loss is not None:
                    body["stop_loss"] = {"stop_price": decimal_text(request.stop_loss)}
            return Plan("POST", "/v2/orders", body)
        if request.action == "close_position":
            position, orders = await self.target(request)
            query = f"?qty={decimal_text(request.volume)}" if request.volume is not None else ""
            # Exit orders hold the position's quantity at Alpaca; the close releases
            # them first (protected_close).
            groups = normalize.protection_groups(
                orders, position.symbol, normalize.exit_side(position), self.canonical
            )
            return Plan("DELETE", f"/v2/positions/{position.id}{query}", None, position, groups)
        if request.action == "cancel_order":
            await self.pending(request)
            return Plan("DELETE", f"/v2/orders/{request.order_id}", None)
        if request.action == "modify_order":
            order = await self.pending(request)
            if (
                request.clear_stop_loss
                or request.clear_take_profit
                or request.stop_loss is not None
                or request.take_profit is not None
            ):
                # A pending bracket's legs are held until the entry fills.
                raise LonoraError("broker_protection_edit_unsupported", 422)
            if request.price is None:
                raise LonoraError("modification_fields_required", 422)
            field = {"limit": "limit_price", "stop": "stop_price"}.get(str(order.get("type")))
            if field is None:
                raise LonoraError("broker_order_type_unsupported", 422)
            return Plan("PATCH", f"/v2/orders/{order['id']}", {field: decimal_text(request.price)})
        # modify_position: add protection, or replace the price of one existing leg.
        if request.clear_stop_loss or request.clear_take_profit:
            # Removing protection widens risk.
            raise LonoraError("broker_protection_clear_unsupported", 422)
        position, orders = await self.target(request)
        groups = normalize.protection_groups(
            orders, position.symbol, normalize.exit_side(position), self.canonical
        )
        if not groups:
            # Protecting an unprotected position: one exit order for the whole quantity,
            # an OCO for both levels, tagged so it reads back as this position's.
            if crypto:
                raise LonoraError("broker_protection_unsupported", 422)
            body = normalize.protection_body(
                position.symbol,
                normalize.exit_side(position),
                position.volume,
                request.stop_loss,
                request.take_profit,
                normalize.protection_tag(request.operation_id, 0),
            )
            return Plan("POST", "/v2/orders", body)
        legs = normalize.protection_legs(orders, position, self.canonical)
        if not legs:
            # Several groups, or one covering part of the position: no single leg to edit.
            raise LonoraError("broker_protection_split", 409)
        edits = [
            (role, wanted)
            for role, wanted, current in (
                ("stop_loss", request.stop_loss, position.stop_loss),
                ("take_profit", request.take_profit, position.take_profit),
            )
            if wanted is not None and wanted != current
        ]
        if not edits:
            raise LonoraError("modification_fields_required", 422)
        if len(edits) > 1:
            # Two legs are two broker mutations; one request sends exactly one.
            raise LonoraError("broker_protection_edit_one_at_a_time", 422)
        role, wanted = edits[0]
        leg = legs.get(role)
        if leg is None:
            raise LonoraError("broker_protection_leg_missing", 409)
        price = "stop_price" if role == "stop_loss" else "limit_price"
        body = {price: decimal_text(wanted)}
        if str(leg.get("client_order_id") or "").startswith(normalize.PROTECTION_PREFIX):
            # A replacement is a new order: keep it recognisable as this position's stop.
            body["client_order_id"] = normalize.protection_tag(request.operation_id, 0)
        return Plan("PATCH", f"/v2/orders/{leg['id']}", body)

    async def target(self, request: TradeRequest) -> tuple[Position, list[dict[str, Any]]]:
        positions, orders = await self.book()
        position = next(
            (
                item
                for item in normalize.positions(positions, orders, self.canonical)
                if item.id == request.position_id and item.symbol == request.symbol
            ),
            None,
        )
        if position is None:
            raise LonoraError("position_not_found", 404)
        return position, orders

    async def pending(self, request: TradeRequest) -> dict[str, Any]:
        _, orders = await self.book()
        order = next(
            (
                item
                for item in normalize.entry_orders(orders)
                if str(item.get("id")) == request.order_id
                and self.canonical(item) == request.symbol
            ),
            None,
        )
        if order is None:
            raise LonoraError("order_not_found", 404)
        return order

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        try:
            plan = await self.prepare(request)
        except LonoraError:
            raise
        except Exception as error:
            raise self.diagnose(error, "trade") from error
        if before_send:
            await before_send()
        # The send boundary is crossed. From here only a received broker answer is a
        # known outcome; anything else stays ambiguous and is never resent.
        if plan.groups and plan.position is not None:
            return await self.protected_close(request, plan, plan.position)
        try:
            response = await self.trading(plan.method, plan.path, body=plan.body)
        except AlpacaHTTPError as error:
            failure = self.diagnose(error, "trade")
            if error.status_code >= 500 or "client_order_id" in error.message.casefold():
                # A server fault may follow the effect; a duplicate identity means an
                # earlier attempt exists. Neither is evidence of non-execution.
                return TradeResult(
                    operation_id=request.operation_id,
                    status="ambiguous",
                    code="broker_result_ambiguous",
                    details={"http_status": error.status_code},
                )
            return TradeResult(
                operation_id=request.operation_id,
                status="failed",
                code=rejection_code(error, request),
                details={
                    "http_status": error.status_code,
                    "broker_code": error.code,
                    "description": failure.diagnostic_message or None,
                    "environment": self.environment,
                },
            )
        except Exception as error:
            self.diagnose(error, "trade")
            return TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )
        try:
            return normalize.trade_result(request, response, self.canonical)
        except Exception as error:
            self.diagnose(error, "trade")
            return TradeResult(
                operation_id=request.operation_id,
                status="ambiguous",
                code="broker_result_ambiguous",
            )

    async def protected_close(
        self, request: TradeRequest, plan: Plan, position: Position
    ) -> TradeResult:
        """Close a protected position: release its exit orders, close, re-arm the rest.

        One executor operation, ordered steps, all recorded in ``details.protection``.
        The close is sent only once every exit order is out of the open book. A close
        that does not happen restores the cancelled protection at the same levels; one
        whose outcome is unknown re-arms nothing (an exit order with nothing held would
        open the opposite position). ``attention`` asks the owner to look whenever the
        position was left, or may be left, without its protection.
        """
        steps: list[dict[str, Any]] = []
        record: dict[str, Any] = {"steps": steps, "cancelled": False, "restored": True}

        def outcome(
            status: Any, code: str | None = None, broker_id: str | None = None, **extra: Any
        ) -> TradeResult:
            exposed = record["cancelled"] and status != "confirmed"
            record["attention"] = exposed or not record["restored"]
            return TradeResult(
                operation_id=request.operation_id,
                status=status,
                code=code,
                broker_id=broker_id,
                details={
                    "environment": self.environment,
                    "position_id": request.position_id,
                    **extra,
                    "protection": record,
                },
            )

        ids = [str(order["id"]) for group in plan.groups for order in group.orders]
        cancelled = True
        for order_id in ids:
            try:
                await self.trading("DELETE", f"/v2/orders/{order_id}")
                record["cancelled"] = True
                steps.append({"step": "cancel", "order_id": order_id, "outcome": "accepted"})
            except AlpacaHTTPError as error:
                if error.status_code in {404, 422}:
                    # Already gone (an OCO sibling, or filled): the book decides below.
                    steps.append({"step": "cancel", "order_id": order_id, "outcome": "closed"})
                    continue
                cancelled = False
                steps.append(
                    {
                        "step": "cancel",
                        "order_id": order_id,
                        "outcome": "refused",
                        "http_status": error.status_code,
                    }
                )
                break
            except Exception as error:
                self.diagnose(error, "trade")
                record["cancelled"] = True  # it may have been applied
                cancelled = False
                steps.append({"step": "cancel", "order_id": order_id, "outcome": "unknown"})
                break
        if not cancelled or not await self.released(ids):
            steps.append({"step": "close", "outcome": "not_sent"})
            record["restored"] = await self.restore(request, plan, steps)
            return outcome("failed", "broker_protection_cancel_failed")
        try:
            closing = normalize.mapping(await self.trading("DELETE", plan.path))
        except AlpacaHTTPError as error:
            if error.status_code < 500:
                failure = self.diagnose(error, "trade")
                steps.append(
                    {"step": "close", "outcome": "refused", "http_status": error.status_code}
                )
                record["restored"] = await self.restore(request, plan, steps)
                return outcome(
                    "failed",
                    rejection_code(error, request),
                    http_status=error.status_code,
                    broker_code=error.code,
                    description=failure.diagnostic_message or None,
                )
            self.diagnose(error, "trade")
            steps.append({"step": "close", "outcome": "unknown"})
            record["restored"] = False
            return outcome("ambiguous", "broker_result_ambiguous")
        except Exception as error:
            self.diagnose(error, "trade")
            steps.append({"step": "close", "outcome": "unknown"})
            record["restored"] = False
            return outcome("ambiguous", "broker_result_ambiguous")
        final = await self.settled(closing)
        state = final.get("status")
        steps.append({"step": "close", "order_id": final.get("id"), "outcome": state})
        details = normalize.order_details(final) if final.get("id") else {}
        if state == "filled":
            record["restored"] = await self.restore(request, plan, steps)
            return outcome("confirmed", broker_id=str(final["id"]), **details)
        if state in normalize.REJECTED or (
            state in normalize.UNFILLED_END
            and normalize.positive_decimal(final.get("filled_qty")) is None
        ):
            record["restored"] = await self.restore(request, plan, steps)
            return outcome("failed", "broker_order_rejected", str(final["id"]), **details)
        # Still working, or partly filled and stopped: what is held is not known yet, so
        # nothing is re-armed.
        record["restored"] = False
        return outcome(
            "ambiguous", "broker_result_ambiguous", str(final.get("id") or "") or None, **details
        )

    async def released(self, ids: list[str]) -> bool:
        """True once none of these orders is in the open book (bounded wait)."""
        wanted = set(ids)
        for attempt in range(POLLS):
            try:
                if not any(str(item.get("id")) in wanted for item in await self.open_orders()):
                    return True
            except Exception as error:
                self.diagnose(error, "trade")
            if attempt + 1 < POLLS:
                await asyncio.sleep(POLL_SECONDS)
        return False

    async def settled(self, order: dict[str, Any]) -> dict[str, Any]:
        """The closing order once it reached a final state, or its last observation."""
        current = order
        for _ in range(POLLS):
            if current.get("status") in {"filled"} | normalize.REJECTED | normalize.UNFILLED_END:
                return current
            await asyncio.sleep(POLL_SECONDS)
            try:
                current = normalize.mapping(await self.trading("GET", f"/v2/orders/{order['id']}"))
            except Exception as error:
                self.diagnose(error, "trade")
        return current

    async def restore(self, request: TradeRequest, plan: Plan, steps: list[dict[str, Any]]) -> bool:
        """Re-arm the original protection, at the same levels, for what is held now.

        A group whose orders are all still working is left alone. Any other group is
        cleared and placed again; a smaller position keeps protection only for what it
        still holds. False whenever the position may be left less protected than before.
        """
        try:
            positions, orders = await self.book()
            position = next(
                (
                    item
                    for item in normalize.positions(positions, orders, self.canonical)
                    if item.id == request.position_id
                ),
                None,
            )
            if position is None:
                steps.append({"step": "restore", "outcome": "position_closed"})
                return True
            states = {str(item["id"]): item.get("status") for item in orders}
            intact = [
                group
                for group in plan.groups
                if all(states.get(str(order["id"])) in INTACT for order in group.orders)
            ]
            broken = [group for group in plan.groups if group not in intact]
            if not broken:
                steps.append({"step": "restore", "outcome": "intact"})
                return True
            leftovers = [
                str(order["id"])
                for group in broken
                for order in group.orders
                if states.get(str(order["id"])) in INTACT
            ]
            for order_id in leftovers:
                await self.trading("DELETE", f"/v2/orders/{order_id}")
                steps.append({"step": "cancel", "order_id": order_id, "outcome": "accepted"})
            if not await self.released([str(o["id"]) for group in broken for o in group.orders]):
                steps.append({"step": "restore", "outcome": "quantity_not_released"})
                return False
            remaining = position.volume - sum((group.qty for group in intact), Decimal(0))
            for index, (qty, group) in enumerate(normalize.rearmed(broken, remaining), start=1):
                body = normalize.protection_body(
                    position.symbol,
                    normalize.exit_side(position),
                    qty,
                    group.stop_loss,
                    group.take_profit,
                    normalize.protection_tag(request.operation_id, index),
                )
                placed = normalize.mapping(await self.trading("POST", "/v2/orders", body=body))
                steps.append(
                    {
                        "step": "rearm",
                        "order_id": placed.get("id"),
                        "qty": str(qty),
                        "stop_loss": str(group.stop_loss) if group.stop_loss else None,
                        "take_profit": str(group.take_profit) if group.take_profit else None,
                    }
                )
            return True
        except Exception as error:
            failure = self.diagnose(error, "trade")
            steps.append({"step": "restore", "outcome": "failed", "code": failure.code})
            return False

    async def reconcile(
        self,
        operation_id: str,
        request: TradeRequest | None = None,
        *,
        submitted_at: datetime | None = None,
    ) -> TradeResult:
        if request is not None and request.action == "modify_position":
            # Protection added to an unprotected position carries its own client order
            # id; an edit of an existing leg does not.
            try:
                await self.assets()
                order = await self.trading(
                    "GET",
                    "/v2/orders:by_client_order_id",
                    params={"client_order_id": normalize.protection_tag(operation_id, 0)},
                )
                found = normalize.mapping(order)
                if found.get("status") not in normalize.REJECTED:
                    return TradeResult(
                        operation_id=operation_id,
                        status="confirmed",
                        broker_id=str(found["id"]),
                        details={**normalize.order_details(found), "reconciled": True},
                    )
            except AlpacaHTTPError as error:
                if error.status_code != 404:
                    raise self.diagnose(error, "reconciliation") from error
            except Exception as error:
                raise self.diagnose(error, "reconciliation") from error
        if request is not None and request.action not in normalize.ENTRY_ACTIONS:
            # Closes, edits and cancels carry no client order id at Alpaca; recovery
            # compares the broker target instead (lonora_trading.target_state).
            return TradeResult(
                operation_id=operation_id,
                status="ambiguous",
                code="execution_not_observed"
                if request.action == "close_position"
                else "mutation_evidence_required",
            )
        try:
            await self.assets()
            try:
                order = await self.trading(
                    "GET",
                    "/v2/orders:by_client_order_id",
                    params={"client_order_id": client_order_id(operation_id)},
                )
            except AlpacaHTTPError as error:
                if error.status_code == 404:
                    return TradeResult(
                        operation_id=operation_id, status="ambiguous", code="execution_not_observed"
                    )
                raise
            return normalize.reconciled(operation_id, request, order, self.canonical)
        except Exception as error:
            raise self.diagnose(error, "reconciliation") from error

    async def close(self) -> None:
        self.closed = True
        await self.client.aclose()
