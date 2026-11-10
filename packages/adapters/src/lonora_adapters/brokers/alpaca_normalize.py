"""Alpaca Trading/Market Data v2 payloads as Lonora contracts. Pure functions, no I/O."""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import broker_operation_tag

from .normalize import observed, positive_decimal

Canonical = Callable[[dict[str, Any]], str]

ENTRY_ACTIONS = {
    "buy": "market",
    "sell": "market",
    "buy_limit": "limit",
    "sell_limit": "limit",
    "buy_stop": "stop",
    "sell_stop": "stop",
}
# Lonora timeframe -> (Alpaca bar timeframe, seconds per bar for the lookback window).
TIMEFRAMES: dict[str, tuple[str, int]] = {
    **{f"{n}m": (f"{n}Min", n * 60) for n in (1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30)},
    **{f"{n}h": (f"{n}Hour", n * 3600) for n in (1, 2, 3, 4, 6, 8, 12)},
    "1d": ("1Day", 86400),
    "1w": ("1Week", 7 * 86400),
    "1mn": ("1Month", 31 * 86400),
}
# Alpaca reports no maximum order size; this bounds sizing arithmetic, not a broker limit.
VOLUME_MAX = Decimal(1_000_000)
STOCK_TICK = Decimal("0.01")
REJECTED = {"rejected"}
UNFILLED_END = {"canceled", "expired", "done_for_day", "stopped", "suspended"}
PROTECTION_ROLES = ("stop_loss", "take_profit")
PROTECTION_PREFIX = "LNP_"


def mapping(value: Any) -> dict[str, Any]:
    """One JSON object from a broker payload; anything else is a malformed response."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("broker_payload_invalid")
    return cast(dict[str, Any], value)


def is_crypto(asset: dict[str, Any]) -> bool:
    return asset.get("class") == "crypto"


def number(value: Any) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("broker_number_invalid")
    return result


def digits(step: Decimal) -> int:
    exponent = step.normalize().as_tuple().exponent
    return max(0, -exponent) if isinstance(exponent, int) else 0


def instrument(asset: dict[str, Any]) -> Instrument:
    symbol = str(asset["symbol"])
    if is_crypto(asset):
        tick = positive_decimal(asset.get("price_increment"))
        minimum = positive_decimal(asset.get("min_order_size"))
        step = positive_decimal(asset.get("min_trade_increment"))
        if tick is None or minimum is None or step is None:
            raise ValueError("broker_crypto_increments_missing")
        base, _, quoted = symbol.partition("/")
        return Instrument(
            symbol=symbol,
            description=str(asset.get("name") or ""),
            digits=min(digits(tick), 12),
            tick_size=tick,
            volume_min=minimum,
            volume_max=VOLUME_MAX,
            volume_step=step,
            point_size=tick,
            contract_size=Decimal(1),
            base_currency=base or None,
            profit_currency=quoted or None,
        )
    # Whole shares: fractional quantities are accepted only for market day orders.
    return Instrument(
        symbol=symbol,
        description=str(asset.get("name") or ""),
        digits=2,
        tick_size=STOCK_TICK,
        volume_min=Decimal(1),
        volume_max=VOLUME_MAX,
        volume_step=Decimal(1),
        point_size=STOCK_TICK,
        contract_size=Decimal(1),
        base_currency=None,
        profit_currency="USD",
    )


def quote(value: dict[str, Any], symbol: str, spec: Instrument, *, account_currency: str) -> Quote:
    bid, ask = positive_decimal(value.get("bp")), positive_decimal(value.get("ap"))
    if bid is None or ask is None or ask < bid:
        # An empty side or a crossed IEX book is no executable price.
        raise LonoraError("quote_unavailable", 404)
    # One unit (share or coin) moving one tick changes P&L by tick_size in the quote
    # currency; that is the account's money only when the currencies agree.
    same = spec.profit_currency is not None and spec.profit_currency == account_currency
    tick_value = spec.tick_size * (spec.contract_size or Decimal(1)) if same else None
    return Quote(
        symbol=symbol,
        bid=bid,
        ask=ask,
        observed_at=observed(value["t"]),
        source="alpaca",
        profit_tick_value=tick_value,
        loss_tick_value=tick_value,
        tick_value_basis="account_currency_per_lot" if tick_value is not None else None,
    )


def candle(value: dict[str, Any], symbol: str, timeframe: str) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        time=observed(value["t"]),
        open=value["o"],
        high=value["h"],
        low=value["l"],
        close=value["c"],
        volume=value.get("v", 0),
    )


def identity(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "login": str(value["account_number"]),
        "server": "paper-api.alpaca.markets",
        "broker": "Alpaca",
        "name": None,
        "platform": "alpaca",
    }


def account(value: dict[str, Any], account_id: str) -> AccountState:
    equity = number(value["equity"])
    margin = number(value.get("initial_margin") or 0)
    blocked = any(
        value.get(key) for key in ("trading_blocked", "account_blocked", "trade_suspended_by_user")
    )
    return AccountState(
        id=account_id,
        **identity(value),
        trade_allowed=value.get("status") == "ACTIVE" and not blocked,
        investor_mode=False,
        currency=str(value.get("currency") or "USD"),
        balance=number(value["cash"]),
        equity=equity,
        margin=margin,
        free_margin=equity - margin,
        observed_at=datetime.now(UTC),
    )


def role(order: dict[str, Any]) -> str | None:
    """The protection role of an open order, or None for an entry.

    Bracket, OTO and OCO legs carry Alpaca's ``group_role``. A standalone stop or limit
    Lonora placed to protect a position carries the ``LNP_`` client order id prefix.
    """
    value = order.get("group_role")
    if value in PROTECTION_ROLES:
        return str(value)
    if str(order.get("client_order_id") or "").startswith(PROTECTION_PREFIX):
        kind = order.get("type")
        if kind in {"stop", "stop_limit"}:
            return "stop_loss"
        if kind == "limit":
            return "take_profit"
    return None


def protection_tag(operation_id: str, index: int) -> str:
    """Client order id of the index-th protection order an operation places."""
    digest = hashlib.sha256(f"{operation_id}:{index}".encode()).hexdigest()
    return PROTECTION_PREFIX + digest[:24]


def entry_orders(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Open orders that open or add exposure: everything except protection orders."""
    return [item for item in orders if role(item) is None]


def legs_of(orders: list[dict[str, Any]], group_id: Any, wanted: str) -> list[dict[str, Any]]:
    return [
        item
        for item in orders
        if group_id is not None and item.get("group_id") == group_id and role(item) == wanted
    ]


def leg_price(leg: dict[str, Any] | None, field: str) -> Decimal | None:
    return positive_decimal(leg.get(field)) if leg else None


@dataclass
class ProtectionGroup:
    """Exit orders that protect one quantity together (one OCO, or one standalone order)."""

    key: str
    orders: list[dict[str, Any]]
    qty: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None

    def leg(self, name: str) -> dict[str, Any] | None:
        return next((item for item in self.orders if role(item) == name), None)


def protection_groups(
    orders: list[dict[str, Any]], symbol: str, exit_side: str, canonical: Canonical
) -> list[ProtectionGroup]:
    """Open protection on a position: exit-side orders of a filled bracket, an OCO, or a
    Lonora standalone stop/limit. Legs of a still-pending entry protect nothing yet."""
    pending = {item.get("group_id") for item in entry_orders(orders) if item.get("group_id")}
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in orders:
        if (
            role(item) is not None
            and item.get("group_id") not in pending
            and canonical(item) == symbol
            and item.get("side") == exit_side
        ):
            key = str(item.get("group_id") or item["id"])
            groups.setdefault(key, []).append(item)
    result: list[ProtectionGroup] = []
    for key, items in groups.items():
        stop = next((item for item in items if role(item) == "stop_loss"), None)
        target = next((item for item in items if role(item) == "take_profit"), None)
        result.append(
            ProtectionGroup(
                key=key,
                orders=items,
                qty=max(
                    number(item.get("qty") or 0) - number(item.get("filled_qty") or 0)
                    for item in items
                ),
                stop_loss=leg_price(stop, "stop_price"),
                take_profit=leg_price(target, "limit_price"),
            )
        )
    return result


def exit_side(position: Position) -> str:
    return "sell" if position.side == "buy" else "buy"


def protection_legs(
    orders: list[dict[str, Any]], position: Position, canonical: Canonical
) -> dict[str, dict[str, Any]]:
    """The legs of the one protection group that covers the whole position.

    Alpaca has no position-level protection. Only a single group on the exit side
    covering the whole quantity reads as the position's stop-loss / take-profit;
    anything else reads as unprotected and is never edited in place.
    """
    groups = protection_groups(orders, position.symbol, exit_side(position), canonical)
    if len(groups) != 1 or groups[0].qty != position.volume:
        return {}
    return {name: leg for name in PROTECTION_ROLES if (leg := groups[0].leg(name)) is not None}


def protection_body(
    symbol: str,
    side: str,
    qty: Decimal,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    tag: str,
) -> dict[str, Any]:
    """One exit order protecting ``qty``: OCO for both levels, else a stop or a limit."""
    body: dict[str, Any] = {
        "symbol": symbol,
        "qty": text(qty),
        "side": side,
        "time_in_force": "gtc",
        "client_order_id": tag,
    }
    if stop_loss is not None and take_profit is not None:
        return {
            **body,
            "type": "limit",
            "limit_price": text(take_profit),
            "order_class": "oco",
            "take_profit": {"limit_price": text(take_profit)},
            "stop_loss": {"stop_price": text(stop_loss)},
        }
    if stop_loss is not None:
        return {**body, "type": "stop", "stop_price": text(stop_loss)}
    if take_profit is not None:
        return {**body, "type": "limit", "limit_price": text(take_profit)}
    raise ValueError("protection_level_required")


def rearmed(
    groups: list[ProtectionGroup], remaining: Decimal
) -> list[tuple[Decimal, ProtectionGroup]]:
    """The protected quantity of each group once only ``remaining`` units are held.

    Levels stay the same; a reduced position gives up protected quantity from the last
    group first, so no exit order ever exceeds what is held.
    """
    plan: list[tuple[Decimal, ProtectionGroup]] = []
    left = remaining
    for group in groups:
        qty = min(group.qty, left)
        if qty > 0:
            plan.append((qty, group))
        left -= qty
    return plan


def text(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("broker_number_invalid")
    return format(value, "f")


def positions(
    values: list[dict[str, Any]], orders: list[dict[str, Any]], canonical: Canonical
) -> list[Position]:
    result: list[Position] = []
    for value in values:
        quantity = abs(number(value["qty"]))
        base = Position(
            id=str(value["asset_id"]),
            symbol=canonical(value),
            side="buy" if value.get("side") == "long" else "sell",
            volume=quantity,
            open_price=number(value["avg_entry_price"]),
            profit=number(value.get("unrealized_pl") or 0),
        )
        legs = protection_legs(orders, base, canonical)
        base.stop_loss = leg_price(legs.get("stop_loss"), "stop_price")
        base.take_profit = leg_price(legs.get("take_profit"), "limit_price")
        result.append(base)
    return result


def order_side(value: dict[str, Any]) -> str:
    side, kind = str(value.get("side")), str(value.get("type"))
    suffix = {"limit": "_limit", "stop": "_stop", "stop_limit": "_stop_limit"}.get(kind, "")
    return side + suffix


def orders(
    values: list[dict[str, Any]], canonical: Canonical, references: dict[str, Decimal]
) -> list[Order]:
    result: list[Order] = []
    for value in entry_orders(values):
        symbol = canonical(value)
        kind = value.get("type")
        price = (
            positive_decimal(value.get("limit_price"))
            if kind == "limit"
            else positive_decimal(value.get("stop_price"))
            if kind in {"stop", "stop_limit"}
            else references.get(symbol)
        )
        if price is None:
            raise ValueError("broker_order_price_missing")
        group = value.get("group_id")
        stop = next(iter(legs_of(values, group, "stop_loss")), None)
        target = next(iter(legs_of(values, group, "take_profit")), None)
        result.append(
            Order(
                id=str(value["id"]),
                symbol=symbol,
                side=order_side(value),
                volume=number(value["qty"]) - number(value.get("filled_qty") or 0),
                price=price,
                stop_loss=leg_price(stop, "stop_price"),
                take_profit=leg_price(target, "limit_price"),
                operation_id=None,
            )
        )
    return result


def fill(value: dict[str, Any], canonical: Canonical) -> dict[str, Any]:
    return {
        "id": str(value["id"]),
        "orderId": value.get("order_id"),
        "symbol": canonical(value),
        "type": value.get("side"),
        "volume": value.get("qty"),
        "price": value.get("price"),
        "time": observed(value["transaction_time"]).isoformat(),
    }


def order_details(value: dict[str, Any]) -> dict[str, Any]:
    filled = positive_decimal(value.get("filled_qty"))
    return {
        "environment": "paper",
        "order_id": str(value["id"]),
        "client_order_id": value.get("client_order_id"),
        "broker_state": value.get("status"),
        "price": str(positive_decimal(value.get("filled_avg_price")))
        if filled is not None and positive_decimal(value.get("filled_avg_price")) is not None
        else None,
        "volume": str(filled) if filled is not None else None,
        "partial_execution": value.get("status") == "partially_filled",
    }


def trade_result(request: TradeRequest, value: Any, canonical: Canonical) -> TradeResult:
    """A received 2xx answer to the one mutation."""
    if request.action == "cancel_order":
        # 204 No Content: the cancel request was accepted.
        return TradeResult(
            operation_id=request.operation_id,
            status="confirmed",
            broker_id=request.order_id,
            details={"environment": "paper", "order_id": request.order_id},
        )
    order = mapping(value)
    if not order.get("id"):
        raise ValueError("broker_order_receipt_invalid")
    if request.action in ENTRY_ACTIONS and order.get("client_order_id") not in {
        None,
        broker_operation_tag(request.operation_id),
    }:
        raise ValueError("broker_order_receipt_mismatch")
    if request.action in ENTRY_ACTIONS and canonical(order) != request.symbol:
        raise ValueError("broker_order_receipt_mismatch")
    details = order_details(order)
    if request.action in {"buy", "sell"}:
        details["position_id"] = str(order.get("asset_id") or "") or None
    if request.action in {"close_position", "modify_position"}:
        details["position_id"] = request.position_id
    if request.action == "modify_order":
        details["replaced_order_id"] = request.order_id
    if order.get("status") in REJECTED:
        return TradeResult(
            operation_id=request.operation_id,
            status="failed",
            broker_id=str(order["id"]),
            code="broker_order_rejected",
            details=details,
        )
    return TradeResult(
        operation_id=request.operation_id,
        status="confirmed",
        broker_id=str(order["id"]),
        details=details,
    )


def reconciled(
    operation_id: str, request: TradeRequest | None, value: Any, canonical: Canonical
) -> TradeResult:
    """The order Alpaca holds under this operation's client order id."""
    order = mapping(value)
    if not order.get("id"):
        raise ValueError("broker_order_receipt_invalid")
    if order.get("client_order_id") != broker_operation_tag(operation_id):
        raise ValueError("broker_order_receipt_mismatch")
    if request is not None and canonical(order) != request.symbol:
        return TradeResult(
            operation_id=operation_id, status="ambiguous", code="execution_not_observed"
        )
    details = {**order_details(order), "reconciled": True}
    if request is not None and request.action in {"buy", "sell"}:
        details["position_id"] = str(order.get("asset_id") or "") or None
    state = order.get("status")
    filled = positive_decimal(order.get("filled_qty"))
    market = request is None or request.action in {"buy", "sell"}
    if state in REJECTED or (market and state in UNFILLED_END and filled is None):
        # Rejected, or a market order that ended without any fill: no exposure exists.
        return TradeResult(
            operation_id=operation_id,
            status="failed",
            broker_id=str(order["id"]),
            code="broker_order_rejected" if state in REJECTED else "broker_order_not_filled",
            details=details,
        )
    return TradeResult(
        operation_id=operation_id, status="confirmed", broker_id=str(order["id"]), details=details
    )
