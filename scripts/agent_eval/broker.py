"""A fake MetaApi terminal under Lonora's real MetaApi adapter.

Acceptance-harness support. ``FakeTerminal`` holds one demo account the way
the owner's broker shows it: suffixed symbols (XAUUSDm, EURUSDm, ...), quotes, candles on
every timeframe, contract specifications, positions, pending orders, modify and close. It
answers in MetaApi's own shapes and raises the SDK's own exceptions, and
``FakeMetaApiBroker`` is the product's ``MetaApiBroker`` with only its SDK connection replaced
by that terminal. Normalisation, error mapping, execution and reconciliation are therefore
the real adapter code. A test double: no network, no SDK client, no credential, no real order.
"""

import asyncio
import importlib
import random
from collections.abc import AsyncGenerator, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, ClassVar, Literal
from unittest.mock import patch
from uuid import uuid4

from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_adapters.brokers.metaapi_provisioning import MetaApiProvisioning
from lonora_contracts.market import Candle, Quote
from lonora_core.user_error import LonoraError

Variant = Literal["m", "c", "pro", "gold"]
TIMEFRAMES = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440, "1w": 10080}
# base symbol: description, digits, contract size, bid, spread, base and profit currency.
# Gold is the price of the owner's conversation ([18]); EURUSD sits between his watch levels.
MARKETS: dict[str, tuple[str, int, int, str, str, str, str]] = {
    "XAUUSD": ("Gold vs US Dollar", 3, 100, "4049.870", "0.240", "XAU", "USD"),
    "XAGUSD": ("Silver vs US Dollar", 3, 5000, "47.512", "0.030", "XAG", "USD"),
    "EURUSD": ("Euro vs US Dollar", 5, 100000, "1.15642", "0.00009", "EUR", "USD"),
    "GBPUSD": ("Great Britain Pound vs US Dollar", 5, 100000, "1.31215", "0.00012", "GBP", "USD"),
    "USDJPY": ("US Dollar vs Japanese Yen", 3, 100000, "153.384", "0.012", "USD", "JPY"),
    "BTCUSD": ("Bitcoin vs US Dollar", 2, 1, "104250.50", "18.00", "BTC", "USD"),
    "USOIL": ("Crude Oil", 3, 1000, "61.420", "0.030", "USOIL", "USD"),
}
METALS = {"XAUUSD": "GOLD", "XAGUSD": "SILVER"}
Fault = Literal["rate_limit", "connection_drop"]


def broker_symbol(base: str, variant: Variant) -> str:
    """How one account names a market: XAUUSDm, XAUUSDc, XAUUSD.pro or GOLD."""
    if variant == "gold":
        return METALS.get(base, base)
    return base + {"m": "m", "c": "c", "pro": ".pro"}[variant]


def sdk_error(name: str, *arguments: Any) -> Exception:
    """An exception of the official SDK, as its websocket client raises it."""
    module = "trade_exception" if name == "TradeException" else "error_handler"
    path = "metaapi_cloud_sdk.clients." + ("metaapi." if module == "trade_exception" else "")
    return getattr(importlib.import_module(path + module), name)(*arguments)


@dataclass
class FakeTerminal:
    """One MetaTrader demo account behind MetaApi's RPC and history calls."""

    account_id: str = "agent-eval-demo"
    variant: Variant = "m"
    balance: Decimal = Decimal("10000")
    known: bool = True
    positions: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    orders: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    deals: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    bids: dict[str, Decimal] = field(default_factory=dict[str, Decimal])
    calls: list[str] = field(default_factory=list[str])
    faults: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    tickets: int = 2217873129
    login: str = "50000001"
    server: str = "Exness-MT5Trial16"

    def __post_init__(self) -> None:
        self.names = {broker_symbol(base, self.variant): base for base in MARKETS}
        for name, base in self.names.items():
            self.bids.setdefault(name, Decimal(MARKETS[base][3]))

    # State the scenarios set up.

    def fail(self, kind: Fault, *, after: int = 0, times: int = 1) -> None:
        """Fail ``times`` broker calls with ``kind`` once ``after`` further calls succeeded."""
        self.faults.append({"kind": kind, "after": after, "times": times})

    def open_position(self, base: str, side: str, volume: str, price: str) -> dict[str, Any]:
        """A position that is already open when the scenario starts."""
        self.tickets += 1
        position = {
            "id": str(self.tickets),
            "symbol": broker_symbol(base, self.variant),
            "type": "POSITION_TYPE_" + side.upper(),
            "volume": float(volume),
            "openPrice": float(price),
            "time": datetime.now(UTC),
        }
        self.positions.append(position)
        return position

    def state(self) -> dict[str, Any]:
        """What a scenario's expected effects are checked against."""
        return {
            "positions": [self.priced(position) for position in self.positions],
            "orders": [dict(order) for order in self.orders],
            "closed_positions": [deal["positionId"] for deal in self.deals if deal.get("exit")],
        }

    # Internals.

    def market(self, symbol: str) -> tuple[str, int, int, str, str, str, str]:
        if symbol not in self.names:
            raise sdk_error("NotFoundException", f"Specification for symbol {symbol} not found")
        return MARKETS[self.names[symbol]]

    def called(self, method: str) -> None:
        self.calls.append(method)
        for fault in self.faults:
            if fault["after"] > 0:
                fault["after"] -= 1
                continue
            if fault["times"] <= 0:
                continue
            fault["times"] -= 1
            if fault["kind"] == "rate_limit":
                raise sdk_error(
                    "TooManyRequestsException",
                    "You have used all your account CPU credits for this period",
                    {"type": "LIMIT_ACCOUNT_SUBSCRIPTIONS_PER_USER", "recommendedRetryTime": None},
                )
            raise ConnectionError("MetaApi websocket client disconnected from the trading server")

    def unknown_account(self) -> Exception:
        return sdk_error(
            "NotFoundException",
            f"Trading account with id {self.account_id} not found",
            "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts/"
            + self.account_id,
        )

    def priced(self, position: dict[str, Any]) -> dict[str, Any]:
        _, digits, contract, _, _, _, _ = self.market(position["symbol"])
        bid, ask = self.quote(position["symbol"])
        buy = position["type"] == "POSITION_TYPE_BUY"
        move = (bid if buy else ask) - Decimal(str(position["openPrice"]))
        profit = (move if buy else -move) * contract * Decimal(str(position["volume"]))
        return {
            **position,
            "currentPrice": float(bid if buy else ask),
            "profit": float(round(self.to_account(position["symbol"], profit), 2)),
            "digits": digits,
        }

    def quote(self, symbol: str) -> tuple[Decimal, Decimal]:
        spread = Decimal(self.market(symbol)[4])
        return self.bids[symbol], self.bids[symbol] + spread

    def to_account(self, symbol: str, amount: Decimal) -> Decimal:
        """An amount in the symbol's profit currency as account currency (USD)."""
        return amount if self.market(symbol)[6] == "USD" else amount / self.bids[symbol]

    def ticket(self) -> str:
        self.tickets += 1
        return str(self.tickets)

    def done(self, **ids: Any) -> dict[str, Any]:
        return {"numericCode": 10009, "stringCode": "TRADE_RETCODE_DONE", "message": "", **ids}

    def check(
        self, symbol: str, volume: float | None, side: str, entry: Decimal, stops: tuple[Any, Any]
    ) -> None:
        """A terminal's own refusals: wrong volume, stops on the wrong side of the price."""
        self.market(symbol)
        if volume is not None:
            lots = Decimal(str(volume))
            if not Decimal("0.01") <= lots <= 200 or lots % Decimal("0.01"):
                raise sdk_error("TradeException", "Invalid volume", 10014, "TRADE_RETCODE_INVALID")
        stop_loss, take_profit = (Decimal(str(v)) if v else None for v in stops)
        below, above = (stop_loss, take_profit) if side == "BUY" else (take_profit, stop_loss)
        if (below is not None and below >= entry) or (above is not None and above <= entry):
            raise sdk_error("TradeException", "Invalid stops", 10016, "TRADE_RETCODE_INVALID_STOPS")

    def find(self, rows: list[dict[str, Any]], identity: str, code: str) -> dict[str, Any]:
        for row in rows:
            if row["id"] == str(identity):
                return row
        raise sdk_error("TradeException", "Position or order not found", 10013, code)

    # MetaApi account entity (REST).

    def entity(self) -> Any:
        if not self.known:
            raise self.unknown_account()
        return SimpleNamespace(
            id=self.account_id,
            state="DEPLOYED",
            login=self.login,
            server=self.server,
            broker="Exness Technologies Ltd",
            name="Standard",
            version=5,
            get_historical_candles=self.get_historical_candles,
        )

    async def get_historical_candles(
        self, symbol: str, timeframe: str, start_time: datetime | None = None, limit: int = 1000
    ) -> list[dict[str, Any]]:
        self.called("get_historical_candles")
        if symbol not in self.names:
            raise sdk_error(
                "NotFoundException",
                f"Symbol {symbol} not found",
                f"https://mt-market-data-client-api-v1.agiliumtrade.ai/symbols/{symbol}",
            )
        minutes = TIMEFRAMES[timeframe]
        digits = self.market(symbol)[1]
        step = timedelta(minutes=minutes)
        now = start_time or datetime.now(UTC)
        opened = datetime.fromtimestamp(
            now.timestamp() // step.total_seconds() * step.total_seconds(), UTC
        )
        # A seeded walk backwards from the live bid: the same account always shows the same
        # history, and the forming candle closes on the quote.
        walk = random.Random(f"{symbol}:{timeframe}")
        close = float(self.bids[symbol])
        candles: list[dict[str, Any]] = []
        for _ in range(limit):
            size = close * 0.0004 * minutes**0.5
            start = close - walk.gauss(0, size)
            high = max(start, close) + abs(walk.gauss(0, size / 2))
            low = min(start, close) - abs(walk.gauss(0, size / 2))
            candles.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": opened,
                    "open": round(start, digits),
                    "high": round(high, digits),
                    "low": round(low, digits),
                    "close": round(close, digits),
                    "tickVolume": walk.randint(200, 2000),
                }
            )
            close, opened = start, opened - step
        return candles[::-1]

    # MetaApi RPC connection.

    async def get_symbols(self) -> list[str]:
        self.called("get_symbols")
        return list(self.names)

    async def get_symbol_specification(self, symbol: str) -> dict[str, Any]:
        self.called("get_symbol_specification")
        description, digits, contract, _, _, base, profit = self.market(symbol)
        point = float(Decimal(1).scaleb(-digits))
        return {
            "symbol": symbol,
            "description": description,
            "digits": digits,
            "point": point,
            "tickSize": point,
            "minVolume": 0.01,
            "maxVolume": 200,
            "volumeStep": 0.01,
            "stopsLevel": 0,
            "contractSize": contract,
            "baseCurrency": base,
            "profitCurrency": profit,
        }

    async def get_symbol_price(self, symbol: str) -> dict[str, Any]:
        self.called("get_symbol_price")
        _, digits, contract, _, _, _, _ = self.market(symbol)
        bid, ask = self.quote(symbol)
        tick = self.to_account(symbol, Decimal(1).scaleb(-digits) * contract)
        return {
            "symbol": symbol,
            "bid": float(bid),
            "ask": float(ask),
            "time": datetime.now(UTC),
            "profitTickValue": float(tick),
            "lossTickValue": float(tick),
        }

    async def get_account_information(self) -> dict[str, Any]:
        self.called("get_account_information")
        profit = sum(Decimal(str(self.priced(p)["profit"])) for p in self.positions)
        equity = self.balance + profit
        return {
            "broker": "Exness Technologies Ltd",
            "currency": "USD",
            "server": self.server,
            "login": self.login,
            "name": "Standard",
            "platform": "mt5",
            "balance": float(self.balance),
            "equity": float(equity),
            "margin": 0,
            "freeMargin": float(equity),
            "leverage": 200,
            "tradeAllowed": True,
            "investorMode": False,
        }

    async def get_positions(self) -> list[dict[str, Any]]:
        self.called("get_positions")
        return [self.priced(position) for position in self.positions]

    async def get_orders(self) -> list[dict[str, Any]]:
        self.called("get_orders")
        return [dict(order) for order in self.orders]

    async def get_deals_by_time_range(self, *_: Any) -> dict[str, Any]:
        self.called("get_deals_by_time_range")
        return {"deals": [dict(deal) for deal in self.deals], "synchronizing": False}

    async def get_history_orders_by_time_range(self, *_: Any) -> dict[str, Any]:
        self.called("get_history_orders_by_time_range")
        return {"historyOrders": [], "synchronizing": False}

    async def market_order(
        self,
        side: str,
        symbol: str,
        volume: float,
        stop_loss: Any,
        take_profit: Any,
        options: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.called("create_market_order")
        bid, ask = self.quote(symbol) if symbol in self.names else (Decimal(0), Decimal(0))
        price = ask if side == "BUY" else bid
        self.check(symbol, volume, side, price, (stop_loss, take_profit))
        client = (options or {}).get("clientId")
        position = {
            "id": self.ticket(),
            "symbol": symbol,
            "type": "POSITION_TYPE_" + side,
            "volume": volume,
            "openPrice": float(price),
            "time": datetime.now(UTC),
            **({"stopLoss": stop_loss} if stop_loss else {}),
            **({"takeProfit": take_profit} if take_profit else {}),
            **({"clientId": client} if client else {}),
        }
        self.positions.append(position)
        deal = {
            "id": self.ticket(),
            "positionId": position["id"],
            "orderId": position["id"],
            "symbol": symbol,
            "type": "DEAL_TYPE_" + side,
            "entryType": "DEAL_ENTRY_IN",
            "volume": volume,
            "price": float(price),
            "time": datetime.now(UTC),
            **({"clientId": client} if client else {}),
        }
        self.deals.append(deal)
        return self.done(
            orderId=position["id"],
            positionId=position["id"],
            dealId=deal["id"],
            price=float(price),
            volume=volume,
        )

    async def create_market_buy_order(
        self, symbol: str, volume: float, stop_loss: Any = None, take_profit: Any = None, **kw: Any
    ) -> dict[str, Any]:
        return await self.market_order(
            "BUY", symbol, volume, stop_loss, take_profit, kw.get("options")
        )

    async def create_market_sell_order(
        self, symbol: str, volume: float, stop_loss: Any = None, take_profit: Any = None, **kw: Any
    ) -> dict[str, Any]:
        return await self.market_order(
            "SELL", symbol, volume, stop_loss, take_profit, kw.get("options")
        )

    async def pending_order(
        self, kind: str, symbol: str, volume: float, price: float, kw: dict[str, Any]
    ) -> dict[str, Any]:
        self.called("create_pending_order")
        side = kind.split("_")[0]
        self.check(
            symbol, volume, side, Decimal(str(price)), (kw.get("stop_loss"), kw.get("take_profit"))
        )
        options: dict[str, Any] = kw.get("options") or {}
        client = options.get("clientId")
        order = {
            "id": self.ticket(),
            "symbol": symbol,
            "type": "ORDER_TYPE_" + kind,
            "state": "ORDER_STATE_PLACED",
            "volume": volume,
            "openPrice": price,
            "time": datetime.now(UTC),
            **({"stopLoss": kw["stop_loss"]} if kw.get("stop_loss") else {}),
            **({"takeProfit": kw["take_profit"]} if kw.get("take_profit") else {}),
            **({"clientId": client} if client else {}),
        }
        self.orders.append(order)
        return self.done(orderId=order["id"])

    async def create_limit_buy_order(
        self, symbol: str, volume: float, price: float, **kw: Any
    ) -> dict[str, Any]:
        return await self.pending_order("BUY_LIMIT", symbol, volume, price, kw)

    async def create_limit_sell_order(
        self, symbol: str, volume: float, price: float, **kw: Any
    ) -> dict[str, Any]:
        return await self.pending_order("SELL_LIMIT", symbol, volume, price, kw)

    async def create_stop_buy_order(
        self, symbol: str, volume: float, price: float, **kw: Any
    ) -> dict[str, Any]:
        return await self.pending_order("BUY_STOP", symbol, volume, price, kw)

    async def create_stop_sell_order(
        self, symbol: str, volume: float, price: float, **kw: Any
    ) -> dict[str, Any]:
        return await self.pending_order("SELL_STOP", symbol, volume, price, kw)

    async def modify_position(
        self, position_id: str, stop_loss: Any = None, take_profit: Any = None
    ) -> dict[str, Any]:
        self.called("modify_position")
        position = self.find(self.positions, position_id, "TRADE_RETCODE_INVALID")
        side = position["type"].removeprefix("POSITION_TYPE_")
        bid, ask = self.quote(position["symbol"])
        self.check(
            position["symbol"], None, side, bid if side == "BUY" else ask, (stop_loss, take_profit)
        )
        # MetaTrader: a modification states both levels; zero or nothing removes one.
        for key, value in (("stopLoss", stop_loss), ("takeProfit", take_profit)):
            if value:
                position[key] = value
            else:
                position.pop(key, None)
        return self.done(positionId=position["id"])

    async def close_position(
        self, position_id: str, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return await self.close_position_partially(position_id, None, options=options)

    async def close_position_partially(
        self, position_id: str, volume: float | None, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        self.called("close_position")
        position = self.find(self.positions, position_id, "TRADE_RETCODE_POSITION_CLOSED")
        priced = self.priced(position)
        closed = position["volume"] if volume is None else volume
        left = round(position["volume"] - closed, 2)
        if left < 0:
            raise sdk_error("TradeException", "Invalid volume", 10014, "TRADE_RETCODE_INVALID")
        if left:
            position["volume"] = left
        else:
            self.positions.remove(position)
        share = Decimal(str(closed)) / Decimal(str(priced["volume"]))
        profit = Decimal(str(priced["profit"])) * share
        self.balance += profit
        client = (options or {}).get("clientId")
        deal = {
            "id": self.ticket(),
            "positionId": position["id"],
            "orderId": self.ticket(),
            "symbol": position["symbol"],
            "type": "DEAL_TYPE_SELL" if "BUY" in position["type"] else "DEAL_TYPE_BUY",
            "entryType": "DEAL_ENTRY_OUT",
            "volume": closed,
            "price": priced["currentPrice"],
            "profit": float(profit),
            "time": datetime.now(UTC),
            "exit": not left,
            **({"clientId": client} if client else {}),
        }
        self.deals.append(deal)
        return self.done(
            orderId=deal["orderId"],
            positionId=position["id"],
            dealId=deal["id"],
            price=priced["currentPrice"],
            volume=closed,
        )

    async def cancel_order(self, order_id: str) -> dict[str, Any]:
        self.called("cancel_order")
        self.orders.remove(self.find(self.orders, order_id, "TRADE_RETCODE_INVALID_ORDER"))
        return self.done(orderId=str(order_id))

    async def modify_order(
        self, order_id: str, open_price: float, stop_loss: Any = None, take_profit: Any = None
    ) -> dict[str, Any]:
        self.called("modify_order")
        order = self.find(self.orders, order_id, "TRADE_RETCODE_INVALID_ORDER")
        order["openPrice"] = open_price
        for key, value in (("stopLoss", stop_loss), ("takeProfit", take_profit)):
            if value:
                order[key] = value
            else:
                order.pop(key, None)
        return self.done(orderId=order["id"])


class FakeMetaApiBroker(MetaApiBroker):
    """Lonora's MetaApi adapter with the SDK connection replaced by a ``FakeTerminal``.

    Constructed with the adapter's own signature, so it stands in wherever the product
    creates a ``MetaApiBroker``. An account id without a registered terminal is refused:
    nothing here can fall through to the real SDK.
    """

    terminals: ClassVar[dict[str, FakeTerminal]] = {}

    def __init__(
        self, account_id: str, region: str | None, token: str, connection_id: str | None = None
    ):
        del region, token
        if account_id not in self.terminals:
            raise LonoraError("agent_eval_account_not_faked", 500)
        self.terminal = self.terminals[account_id]
        self.account_id, self.connection_id = account_id, connection_id
        self._log_redactions = ()
        self.account_instance: Any = None
        self.rpc: Any = None
        self.streaming: Any = None
        self.evidence = None
        self.lock, self.stream_lock = asyncio.Lock(), asyncio.Lock()
        self.evidence_lock = asyncio.Lock()
        self._history_billing_failure = None
        self._history_billing_retry_at = 0.0
        self._history_billing_probe = False
        self._closing = False

    async def resolve_account(self) -> Any:
        try:
            self.account_instance = self.terminal.entity()
            return self.account_instance
        except Exception as error:
            raise self.diagnose(error, "account") from error

    async def prepare(self) -> Any:
        await self.resolve_account()
        return self.terminal

    async def prepare_stream(self) -> Any:
        # No streaming connection: every read takes the adapter's RPC path.
        raise LonoraError("broker_connection_unavailable", 502)

    async def stream_quotes(self, symbol: str) -> AsyncGenerator[Quote, None]:
        yield await self.quote(symbol)
        await asyncio.Event().wait()

    async def stream_candles(self, symbol: str, timeframe: str) -> AsyncGenerator[Candle, None]:
        yield (await self.candles(symbol, timeframe, 1))[-1]
        await asyncio.Event().wait()

    async def close(self) -> None:
        self._closing = True


@contextmanager
def installed(*terminals: FakeTerminal) -> Generator[None]:
    """Every MetaApi broker the product creates inside the block is one of these terminals."""
    previous = dict(FakeMetaApiBroker.terminals)
    FakeMetaApiBroker.terminals.update({terminal.account_id: terminal for terminal in terminals})
    try:
        with (
            patch("lonora_adapters.brokers.metaapi.MetaApiBroker", FakeMetaApiBroker),
            patch("lonora_trading.connections.MetaApiBroker", FakeMetaApiBroker),
        ):
            yield
    finally:
        FakeMetaApiBroker.terminals.clear()
        FakeMetaApiBroker.terminals.update(previous)


# MetaApi provisioning (account entities, REST).

UPDATE_FIELDS = (
    "name",
    "server",
    "magic",
    "manualTrades",
    "slippage",
    "quoteStreamingIntervalInSeconds",
    "tags",
    "metadata",
    "resourceSlots",
    "copyFactoryResourceSlots",
)
PROVISIONING_URL = (
    "https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai/users/current/accounts"
)


class FakeAccountEntity:
    """One MetaApi account entity: state and connection status, no terminal connection."""

    def __init__(self, api: "FakeProvisioningApi", data: dict[str, Any]):
        self.api, self._data = api, data

    def __getattr__(self, name: str) -> Any:
        keys = {"id": "_id", "connection_status": "connectionStatus"}
        data = self.__dict__["_data"]
        key = keys.get(name, name)
        if key not in data:
            raise AttributeError(name)
        return data[key]

    def get_rpc_connection(self) -> Any:
        raise AssertionError("provisioning must never open an RPC connection")

    def get_streaming_connection(self, *_: Any) -> Any:
        raise AssertionError("provisioning must never open a streaming connection")

    async def reload(self) -> None:
        self.api.called("reload")
        self._data = self.api.stored(self._data["_id"])

    async def deploy(self) -> None:
        self.api.called("deploy")
        self.api.start(self._data["_id"])
        await self.reload()

    async def undeploy(self) -> None:
        self.api.called("undeploy")
        self.api.stored(self._data["_id"])["state"] = "UNDEPLOYING"
        await self.reload()

    async def redeploy(self) -> None:
        self.api.called("redeploy")
        self.api.start(self._data["_id"])
        await self.reload()

    async def update(self, account: dict[str, Any]) -> None:
        # A PUT: an update field left out is reset. A new password is used by the
        # terminal only after the next deploy or redeploy.
        self.api.called("update")
        self.api.updates.append({key: value for key, value in account.items() if key != "password"})
        data = self.api.stored(self._data["_id"])
        for key in UPDATE_FIELDS:
            data.pop(key, None)
        data.update(account)
        await self.reload()

    async def remove(self) -> None:
        self.api.called("remove")
        self.api.stored(self._data["_id"])
        del self.api.accounts[self._data["_id"]]


@dataclass
class FakeProvisioningApi:
    """MetaApi's ``metatrader_account_api`` for one token, in the SDK's shapes and exceptions.

    ``servers`` maps a broker server to the logins it knows and their master passwords.
    A created account is deploying; the next read finds it deployed, and connected to the
    broker only while its stored password is the server's. No network, no real account.
    """

    servers: dict[str, dict[str, str]] = field(
        default_factory=lambda: {"Exness-MT5Trial16": {"50000001": "fixture-master-password"}}
    )
    accounts: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    token_valid: bool = True
    calls: list[str] = field(default_factory=list[str])
    creates: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    updates: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])
    # "after_commit": MetaApi creates the account and the answer is lost on the way back;
    # "before_commit": the request is lost before MetaApi saw it.
    lose_create_answer: Literal["after_commit", "before_commit"] | None = None
    # The create succeeds, then the SDK's read of the new account fails once (429).
    lose_read_after_create: bool = False
    unreadable: set[str] = field(default_factory=set[str])
    transactions: list[str] = field(default_factory=list[str])
    by_transaction: dict[str, str] = field(default_factory=dict[str, str])
    sequence: int = 0
    # Account ids are unique per fake, so tests sharing a database never collide.
    prefix: str = field(default_factory=lambda: "fixture-metaapi-" + uuid4().hex[:8])

    def called(self, method: str) -> None:
        self.calls.append(method)
        if not self.token_valid:
            raise sdk_error(
                "UnauthorizedException", "Authorization token invalid", PROVISIONING_URL
            )

    def link(
        self, login: str, server: str, *, region: str = "london", deployed: bool = True
    ) -> str:
        """An account the owner created at metaapi.cloud before Lonora provisioned anything."""
        self.sequence += 1
        account_id = f"{self.prefix}-{self.sequence:04d}"
        self.accounts[account_id] = {
            "_id": account_id,
            "login": login,
            "server": server,
            "version": 5,
            "region": region,
            "name": "owner linked",
            "magic": 123456,
            "slippage": 2.5,
            "tags": ["owner"],
            "password": self.servers.get(server, {}).get(login, ""),
            "terminal_password": self.servers.get(server, {}).get(login, ""),
            "state": "DEPLOYED" if deployed else "UNDEPLOYED",
            "connectionStatus": "CONNECTED" if deployed else "DISCONNECTED",
        }
        return account_id

    def stored(self, account_id: str) -> dict[str, Any]:
        data = self.accounts.get(account_id)
        if data is None:
            raise sdk_error(
                "NotFoundException",
                "Trading account not found",
                PROVISIONING_URL + "/" + account_id,
            )
        settle = {"DEPLOYING": "DEPLOYED", "UNDEPLOYING": "UNDEPLOYED"}
        data["state"] = settle.get(data["state"], data["state"])
        expected = self.servers.get(data["server"], {}).get(data["login"])
        right = expected == data["terminal_password"]
        data["connectionStatus"] = (
            ("CONNECTED" if right else "DISCONNECTED_FROM_BROKER")
            if data["state"] == "DEPLOYED"
            else "DISCONNECTED"
        )
        return data

    def start(self, account_id: str) -> None:
        data = self.stored(account_id)
        data["state"], data["terminal_password"] = "DEPLOYING", data["password"]

    def entity(self, account_id: str) -> FakeAccountEntity:
        return FakeAccountEntity(self, dict(self.stored(account_id)))

    async def get_account(self, account_id: str) -> FakeAccountEntity:
        self.called("get_account")
        if account_id in self.unreadable:
            self.unreadable.discard(account_id)
            raise sdk_error("TooManyRequestsException", "Rate limited", {}, PROVISIONING_URL)
        return self.entity(account_id)

    async def get_accounts_with_infinite_scroll_pagination(
        self, accounts_filter: dict[str, Any] | None = None
    ) -> list[FakeAccountEntity]:
        self.called("list")
        options = accounts_filter or {}
        query = str(options.get("query") or "")
        offset, limit = int(options.get("offset", 0)), int(options.get("limit", 1000))
        rows = [
            account_id
            for account_id, data in sorted(self.accounts.items())
            if not query
            or any(query in str(data[key]) for key in ("_id", "name", "server", "login"))
        ]
        return [self.entity(account_id) for account_id in rows[offset : offset + limit]]

    @property
    def _metatrader_account_client(self) -> Any:
        """The SDK account client's surface the provisioning client posts a create with."""
        api = self

        class HttpClient:
            async def request(self, options: dict[str, Any], kind: str) -> dict[str, Any]:
                assert kind == "create_account" and options["method"] == "POST"
                transaction = options["headers"]["transaction-id"]
                api.transactions.append(transaction)
                if transaction in api.by_transaction:
                    # MetaApi answers a repeated transaction id with the same account.
                    return {"id": api.by_transaction[transaction], "state": "DEPLOYING"}
                created = await api.create_account(options["body"], transaction)
                if api.lose_read_after_create:
                    api.lose_read_after_create = False
                    api.unreadable.add(created.id)
                return {"id": created.id, "state": "DEPLOYING"}

        return SimpleNamespace(
            _is_not_jwt_token=lambda: False,
            _host="https://mt-provisioning-api-v1.agiliumtrade.agiliumtrade.ai",
            _token="fixture",
            _http_client=HttpClient(),
        )

    async def create_account(
        self, account: dict[str, Any], transaction: str | None = None
    ) -> FakeAccountEntity:
        self.called("create_account")
        self.creates.append({key: value for key, value in account.items() if key != "password"})
        server = self.servers.get(account["server"])
        if server is None:
            raise sdk_error(
                "ValidationException",
                "We were unable to retrieve the server file for this broker",
                {"code": "E_SRV_NOT_FOUND"},
                PROVISIONING_URL,
            )
        if server.get(account["login"]) != account["password"]:
            raise sdk_error(
                "ValidationException",
                "We failed to authenticate to your broker using credentials provided",
                {"code": "E_AUTH"},
                PROVISIONING_URL,
            )
        lost = sdk_error("ApiException", None, None, PROVISIONING_URL)  # an httpx read timeout
        if self.lose_create_answer == "before_commit":
            self.lose_create_answer = None
            raise lost
        self.sequence += 1
        account_id = f"{self.prefix}-{self.sequence:04d}"
        self.accounts[account_id] = {
            "_id": account_id,
            "terminal_password": account["password"],
            "version": 5 if account["platform"] == "mt5" else 4,
            "region": account.get("region", "new-york"),
            "state": "DEPLOYING",
            "connectionStatus": "DISCONNECTED",
            **{key: account[key] for key in ("login", "server", "name", "password", "magic")},
        }
        if transaction:
            self.by_transaction[transaction] = account_id
        if self.lose_create_answer == "after_commit":
            self.lose_create_answer = None
            raise lost
        return FakeAccountEntity(self, dict(self.accounts[account_id]))


class FakeMetaApiProvisioning(MetaApiProvisioning):
    """Lonora's provisioning client with only the SDK's account API replaced."""

    def __init__(self, api: FakeProvisioningApi, token: str = "fixture.metaapi.token"):
        self.api = SimpleNamespace(metatrader_account_api=api, close=lambda: None)
        self._redactions = (token,)
