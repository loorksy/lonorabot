"""A local fake Alpaca paper server (Trading v2 + Market Data) for adapter tests.

It answers the requests the adapter makes, with Alpaca's documented JSON shapes (as
recorded in tests/fixtures/alpaca), and keeps a small order book: market orders fill at
the quote, brackets leave group legs (``group_id``/``group_role``), replace creates a new
order id, and closing a position whose quantity is held by legs is refused with 403 as
Alpaca does. Nothing here reaches the network.
"""

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

FIXTURES = Path(__file__).parent / "fixtures" / "alpaca"
KEY_ID, SECRET_KEY = "PKTESTKEYID000000000", "test-secret-key-0000000000000000000000"


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def error(status: int, code: int, message: str) -> JSONResponse:
    return JSONResponse({"code": code, "message": message}, status_code=status)


class FakeAlpaca:
    def __init__(self) -> None:
        self.account: dict[str, Any] = fixture("account.json")
        self.assets: list[dict[str, Any]] = fixture("assets.json")
        self.quotes: dict[str, dict[str, Any]] = fixture("quotes.json")
        self.bars: dict[str, list[dict[str, Any]]] = fixture("bars.json")
        self.positions: dict[str, dict[str, Any]] = {}
        self.orders: dict[str, dict[str, Any]] = {}
        self.fills: list[dict[str, Any]] = []
        self.is_open = True
        self.mutations: list[tuple[str, str]] = []
        self.requests: list[tuple[str, str]] = []
        self.seen_hosts: set[str] = set()
        self.fail_next: dict[str, tuple[int, int, str]] = {}
        self.app = Starlette(
            routes=[
                Route("/v2/account", self.get_account),
                Route("/v2/clock", self.clock),
                Route("/v2/assets", self.list_assets),
                Route("/v2/positions", self.list_positions),
                Route("/v2/positions/{key}", self.close_position, methods=["DELETE"]),
                Route("/v2/orders", self.list_orders, methods=["GET"]),
                Route("/v2/orders", self.place, methods=["POST"]),
                Route("/v2/orders:by_client_order_id", self.by_client_id),
                Route("/v2/orders/{order_id}", self.replace, methods=["PATCH"]),
                Route("/v2/orders/{order_id}", self.cancel, methods=["DELETE"]),
                Route("/v2/account/activities/FILL", self.activities),
                Route("/v2/stocks/quotes/latest", self.latest_quotes),
                Route("/v1beta3/crypto/us/latest/quotes", self.latest_quotes),
                Route("/v2/stocks/bars", self.list_bars),
                Route("/v1beta3/crypto/us/bars", self.list_bars),
            ]
        )

    # -- plumbing ----------------------------------------------------------------------

    def transport(self) -> "Transport":
        return Transport(self)

    def asset(self, key: str) -> dict[str, Any] | None:
        compact = key.replace("/", "")
        return next(
            (
                a
                for a in self.assets
                if key in {a["id"], a["symbol"]} or a["symbol"].replace("/", "") == compact
            ),
            None,
        )

    def guard(self, request: Request) -> Response | None:
        if (
            request.headers.get("APCA-API-KEY-ID") != KEY_ID
            or request.headers.get("APCA-API-SECRET-KEY") != SECRET_KEY
        ):
            return error(401, 40110000, "request is not authorized")
        key = request.method + " " + request.url.path
        injected = self.fail_next.pop(key, None)
        if injected:
            return error(*injected)
        return None

    def order(self, **fields: Any) -> dict[str, Any]:
        asset = self.asset(fields["symbol"])
        assert asset is not None
        value: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "client_order_id": str(uuid.uuid4()),
            "created_at": now(),
            "updated_at": now(),
            "submitted_at": now(),
            "filled_at": None,
            "canceled_at": None,
            "replaced_by": None,
            "replaces": None,
            "asset_id": asset["id"],
            "symbol": asset["symbol"],
            "asset_class": asset["class"],
            "qty": "0",
            "filled_qty": "0",
            "filled_avg_price": None,
            "order_class": "simple",
            "type": "market",
            "side": "buy",
            "time_in_force": "day",
            "limit_price": None,
            "stop_price": None,
            "status": "new",
            "extended_hours": False,
            "legs": None,
        }
        value.update(fields)
        value["symbol"] = asset["symbol"]
        self.orders[value["id"]] = value
        return value

    def fill(self, order: dict[str, Any], price: Decimal) -> None:
        asset = self.asset(order["symbol"])
        assert asset is not None
        qty = Decimal(order["qty"])
        signed = qty if order["side"] == "buy" else -qty
        held = self.positions.get(asset["id"])
        current = (
            Decimal(held["qty"]) * (1 if held and held["side"] == "long" else -1)
            if held
            else Decimal(0)
        )
        total = current + signed
        order.update(
            status="filled", filled_qty=str(qty), filled_avg_price=str(price), filled_at=now()
        )
        self.fills.append(
            {
                "id": f"{datetime.now(UTC):%Y%m%d%H%M%S%f}::{uuid.uuid4()}",
                "activity_type": "FILL",
                "transaction_time": now(),
                "type": "fill",
                "price": str(price),
                "qty": str(qty),
                "side": order["side"],
                "symbol": asset["symbol"].replace("/", ""),
                "order_id": order["id"],
            }
        )
        if total == 0:
            self.positions.pop(asset["id"], None)
        else:
            self.positions[asset["id"]] = {
                "asset_id": asset["id"],
                # Alpaca spells crypto positions without the slash.
                "symbol": asset["symbol"].replace("/", ""),
                "exchange": asset["exchange"],
                "asset_class": asset["class"],
                "avg_entry_price": str(price) if not held else held["avg_entry_price"],
                "qty": str(abs(total)),
                "qty_available": str(abs(total)),
                "side": "long" if total > 0 else "short",
                "unrealized_pl": "0",
                "cost_basis": str(abs(total) * price),
            }
        if order.get("group_id") and order.get("group_role") == "entry":
            for leg in self.orders.values():
                if leg.get("group_id") == order["group_id"] and leg["status"] == "held":
                    leg["status"] = "new"

    def price(self, symbol: str, side: str) -> Decimal:
        quote = self.quotes[symbol]
        return Decimal(str(quote["ap" if side == "buy" else "bp"]))

    def held(self, asset_id: str) -> Decimal:
        """Quantity reserved by open exit legs; the two legs of one group share it."""
        groups: dict[str, Decimal] = {}
        for o in self.orders.values():
            if (
                o["asset_id"] == asset_id
                and o.get("group_role") in {"stop_loss", "take_profit"}
                and o["status"] in {"new", "held", "accepted"}
            ):
                groups[o["group_id"]] = max(
                    groups.get(o["group_id"], Decimal(0)), Decimal(o["qty"])
                )
        return sum(groups.values(), Decimal(0))

    # -- trading API -------------------------------------------------------------------

    async def get_account(self, request: Request) -> Response:
        return self.guard(request) or JSONResponse(self.account)

    async def clock(self, request: Request) -> Response:
        return self.guard(request) or JSONResponse(
            {"timestamp": now(), "is_open": self.is_open, "next_open": now(), "next_close": now()}
        )

    async def list_assets(self, request: Request) -> Response:
        wanted = request.query_params.get("asset_class")
        return self.guard(request) or JSONResponse(
            [a for a in self.assets if wanted in {None, a["class"]}]
        )

    async def list_positions(self, request: Request) -> Response:
        return self.guard(request) or JSONResponse(list(self.positions.values()))

    async def list_orders(self, request: Request) -> Response:
        open_states = {"new", "accepted", "pending_new", "partially_filled", "held"}
        return self.guard(request) or JSONResponse(
            [o for o in self.orders.values() if o["status"] in open_states]
        )

    async def by_client_id(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        tag = request.query_params.get("client_order_id")
        found = next((o for o in self.orders.values() if o["client_order_id"] == tag), None)
        return JSONResponse(found) if found else error(404, 40410000, "order not found")

    async def place(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        body = await request.json()
        self.mutations.append(("POST", "/v2/orders"))
        asset = self.asset(body["symbol"])
        if asset is None:
            return error(422, 40010001, "asset not found")
        if any(o["client_order_id"] == body.get("client_order_id") for o in self.orders.values()):
            return error(422, 40010001, "client_order_id must be unique")
        qty = Decimal(body["qty"])
        side, kind = body["side"], body["type"]
        held = self.positions.get(asset["id"])
        if side == "sell" and asset["class"] == "crypto" and not held:
            return error(403, 40310000, "insufficient balance for BTC (requested: 1, available: 0)")
        cost = qty * self.price(asset["symbol"], side)
        if side == "buy" and cost > Decimal(self.account["buying_power"]):
            return error(403, 40310000, "insufficient buying power")
        group = str(uuid.uuid4()) if body.get("order_class") in {"bracket", "oto"} else None
        exit_side = "sell" if side == "buy" else "buy"
        entry = self.order(
            symbol=asset["symbol"],
            client_order_id=body.get("client_order_id") or str(uuid.uuid4()),
            qty=str(qty),
            side=side,
            type=kind,
            time_in_force=body["time_in_force"],
            limit_price=body.get("limit_price"),
            stop_price=body.get("stop_price"),
            order_class=body.get("order_class", "simple"),
            **({"group_id": group, "group_role": "entry"} if group else {}),
        )
        legs: list[dict[str, Any]] = []
        if group and body.get("take_profit"):
            legs.append(
                self.order(
                    symbol=asset["symbol"],
                    qty=str(qty),
                    side=exit_side,
                    type="limit",
                    time_in_force=body["time_in_force"],
                    status="held",
                    limit_price=body["take_profit"]["limit_price"],
                    order_class=body["order_class"],
                    group_id=group,
                    group_role="take_profit",
                )
            )
        if group and body.get("stop_loss"):
            legs.append(
                self.order(
                    symbol=asset["symbol"],
                    qty=str(qty),
                    side=exit_side,
                    type="stop",
                    time_in_force=body["time_in_force"],
                    status="held",
                    stop_price=body["stop_loss"]["stop_price"],
                    order_class=body["order_class"],
                    group_id=group,
                    group_role="stop_loss",
                )
            )
        if kind == "market":
            self.fill(entry, self.price(asset["symbol"], side))
        else:
            entry["status"] = "accepted"
        return JSONResponse({**entry, "legs": legs or None})

    async def replace(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        self.mutations.append(("PATCH", request.url.path))
        old = self.orders.get(request.path_params["order_id"])
        if old is None:
            return error(404, 40410000, "order not found")
        if old["status"] not in {"new", "accepted", "held"}:
            return error(422, 42210000, "order is not replaceable")
        body = await request.json()
        new = self.order(
            **{
                k: v
                for k, v in old.items()
                if k not in {"id", "status", "replaces", "client_order_id"}
            },
            status=old["status"],
            replaces=old["id"],
        )
        new.update({k: v for k, v in body.items() if v is not None})
        old.update(status="replaced", replaced_by=new["id"])
        return JSONResponse(new)

    async def cancel(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        self.mutations.append(("DELETE", request.url.path))
        order = self.orders.get(request.path_params["order_id"])
        if order is None:
            return error(404, 40410000, "order not found")
        if order["status"] not in {"new", "accepted", "held", "partially_filled"}:
            return error(422, 42210000, "order is not cancelable")
        order.update(status="canceled", canceled_at=now())
        for leg in self.orders.values():
            if (
                order.get("group_id")
                and leg.get("group_id") == order["group_id"]
                and leg is not order
            ):
                if leg["status"] in {"held", "new"}:
                    leg.update(status="canceled", canceled_at=now())
        return Response(status_code=204)

    async def close_position(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        self.mutations.append(("DELETE", request.url.path))
        asset = self.asset(request.path_params["key"])
        position = self.positions.get(asset["id"]) if asset else None
        if position is None or asset is None:
            return error(404, 40410000, "position does not exist")
        qty = Decimal(request.query_params.get("qty") or position["qty"])
        available = Decimal(position["qty"]) - self.held(asset["id"])
        if qty > available:
            return error(
                403,
                40310000,
                f"insufficient qty available for order (requested: {qty}, available: {available})",
            )
        side = "sell" if position["side"] == "long" else "buy"
        order = self.order(symbol=asset["symbol"], qty=str(qty), side=side, type="market")
        self.fill(order, self.price(asset["symbol"], side))
        return JSONResponse(order)

    async def activities(self, request: Request) -> Response:
        return self.guard(request) or JSONResponse(list(reversed(self.fills)))

    # -- market data -------------------------------------------------------------------

    async def latest_quotes(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        symbols = request.query_params["symbols"].split(",")
        # Served as the latest observation, stamped now, as a live feed would be.
        return JSONResponse(
            {"quotes": {s: {**self.quotes[s], "t": now()} for s in symbols if s in self.quotes}}
        )

    async def list_bars(self, request: Request) -> Response:
        if refused := self.guard(request):
            return refused
        symbol, frame = request.query_params["symbols"], request.query_params["timeframe"]
        rows = list(self.bars.get(f"{symbol}:{frame}", []))
        if request.query_params.get("sort") == "desc":
            rows.reverse()
        limit = int(request.query_params.get("limit", "1000"))
        return JSONResponse({"bars": {symbol: rows[:limit]}, "next_page_token": None})


class Transport(httpx.AsyncBaseTransport):
    """The fake server behind the adapter's fixed paper URLs, with response-loss faults.

    ``lose_after`` forwards the request (the effect happens) and then raises a read
    timeout; ``lose_before`` raises a connect timeout without forwarding it.
    """

    def __init__(self, fake: FakeAlpaca):
        self.fake = fake
        self.inner = httpx.ASGITransport(fake.app)
        self.lose_after: set[str] = set()
        self.lose_before: set[str] = set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.fake.seen_hosts.add(request.url.host)
        assert request.url.host in {"paper-api.alpaca.markets", "data.alpaca.markets"}
        key = request.method + " " + request.url.path
        self.fake.requests.append((request.method, request.url.path))
        if key in self.lose_before:
            self.lose_before.discard(key)
            raise httpx.ConnectTimeout("explicit loss before the request", request=request)
        response = await self.inner.handle_async_request(request)
        if key in self.lose_after:
            self.lose_after.discard(key)
            await response.aread()
            raise httpx.ReadTimeout("explicit loss after the effect", request=request)
        return response
