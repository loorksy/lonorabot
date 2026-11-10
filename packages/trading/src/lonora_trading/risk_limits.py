"""Monetary risk enforcement at the financial boundary, from broker tick economics.

The owner's optional limits (``ExecutionPolicy.risk``) are checked inside the
executor's before-send callback, under the per-account send lock, against a fresh broker
snapshot. Only requests that are not risk-reducing (``admission.risk_reducing``) are
checked: closing, cancelling and tightening a stop are always admissible.

Risk at a stop uses the same Decimal arithmetic as the read-only sizing estimate
(``position_sizing``): whole ticks between the reference price and the stop-loss,
rounded up, times the broker's per-lot loss tick value in account currency, times the
volume. The reference is the executable entry (ask for a buy, bid for a sell, the order
price for a pending entry) and, for an open position, the current closing price. A
position, order or operation without a stop-loss has unbounded modeled risk.

Open risk counts, conservatively, every open position and pending order plus the
operations whose effect may not be visible in broker state yet: ``submitted`` and
``ambiguous`` entries, and confirmed entries still awaiting state verification, unless
their resulting ticket is already in the snapshot. An unresolved stop or pending-order
edit counts as the worse of the current and the requested state.

Daily loss is broker-reported realized P&L since local midnight in the owner's
trading-day time zone, plus the current floating profit of open positions. Deals count
conservatively (``deal_pnl``): trade deals (``DEAL_TYPE_BUY``/``DEAL_TYPE_SELL``) with
their profit, commission and swap; balance, credit and bonus cash flows not at all; and
every other deal type (correction, charge, commission, interest, dividend, tax, a
cancelled deal, an unknown or missing type) only when its total is negative, so a
non-trading credit never offsets a trading loss. Incomplete or unreadable history
blocks new risk rather than being treated as zero loss.
"""

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time
from decimal import ROUND_CEILING, Decimal, InvalidOperation, localcontext
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.market import Instrument, Quote
from lonora_contracts.risk_limits import DailyLoss, MonetaryRiskLimits, RiskAssessment, RiskItem
from lonora_contracts.trading import UNRESOLVED_STATUSES, TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingJournalRow
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import ENTRY_ACTIONS, direction

HISTORY_LIMIT = 1000
ECONOMICS_TIMEOUT_SECONDS = 20
# Deal types by their ``DEAL_TYPE_`` suffix (MetaTrader/MetaApi names).
TRADE_DEALS = frozenset({"BUY", "SELL"})
CASH_FLOW_DEALS = frozenset({"BALANCE", "CREDIT", "BONUS"})
MODIFICATIONS = frozenset({"modify_position", "modify_order"})
# Actions whose result is itself a trade with a stop: the per-trade ceiling applies.
TRADE_LIMIT_ACTIONS = ENTRY_ACTIONS | MODIFICATIONS
MAX_ITEMS = 100


class RiskReader(Protocol):
    async def instrument(self, symbol: str) -> Instrument: ...
    async def quote(self, symbol: str) -> Quote: ...
    async def history(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class Economics:
    symbol: str
    tick_size: Decimal
    loss_tick_value: Decimal
    bid: Decimal
    ask: Decimal


def economics(instrument: Instrument, quote: Quote) -> Economics:
    loss = quote.loss_tick_value
    if (
        instrument.symbol != quote.symbol
        or quote.tick_value_basis != "account_currency_per_lot"
        or loss is None
        or not loss.is_finite()
        or loss <= 0
        or not instrument.tick_size.is_finite()
        or instrument.tick_size <= 0
    ):
        raise LonoraError("risk_economics_unavailable", 409)
    return Economics(quote.symbol, instrument.tick_size, loss, quote.bid, quote.ask)


def stop_risk(
    value: Economics, side: str, reference: Decimal, stop_loss: Decimal, volume: Decimal
) -> Decimal:
    """Modeled loss moving from ``reference`` to ``stop_loss``; zero if already beyond it."""
    with localcontext() as context:
        context.prec = 64
        distance = reference - stop_loss if side == "buy" else stop_loss - reference
        if distance <= 0:
            return Decimal(0)
        ticks = (distance / value.tick_size).to_integral_value(rounding=ROUND_CEILING)
        return ticks * value.loss_tick_value * volume


def closing_price(value: Economics, side: str) -> Decimal:
    return value.bid if side == "buy" else value.ask


def entry_price(value: Economics, side: str) -> Decimal:
    return value.ask if side == "buy" else value.bid


def item_risk(
    value: Economics | None,
    side: str,
    reference: Decimal | None,
    stop_loss: Decimal | None,
    volume: Decimal,
) -> Decimal | None:
    if stop_loss is None or side == "unknown":
        return None
    if value is None or reference is None:
        raise LonoraError("risk_economics_unavailable", 409)
    return stop_risk(value, side, reference, stop_loss, volume)


def position_item(position: Position, value: Economics | None) -> RiskItem:
    side = direction(position.side)
    reference = closing_price(value, side) if value is not None and side != "unknown" else None
    return RiskItem(
        kind="position",
        id=position.id,
        symbol=position.symbol,
        side=side,
        volume=position.volume,
        reference_price=reference,
        stop_loss=position.stop_loss,
        risk=item_risk(value, side, reference, position.stop_loss, position.volume),
    )


def order_item(order: Order, value: Economics | None) -> RiskItem:
    side = direction(order.side)
    return RiskItem(
        kind="order",
        id=order.id,
        symbol=order.symbol,
        side=side,
        volume=order.volume,
        reference_price=order.price,
        stop_loss=order.stop_loss,
        risk=item_risk(value, side, order.price, order.stop_loss, order.volume),
    )


def modified_stop(request: TradeRequest, current: Decimal | None) -> Decimal | None:
    if request.clear_stop_loss:
        return None
    return request.stop_loss if request.stop_loss is not None else current


def requested_item(
    request: TradeRequest,
    snapshot: ExecutionSnapshot,
    values: dict[str, Economics],
    *,
    kind: str,
    identity: str,
) -> RiskItem | None:
    """The trade a request would leave behind; None when it creates or edits no trade."""
    value = values.get(request.symbol)
    if request.action in ENTRY_ACTIONS:
        side = direction(request.action)
        assert request.volume is not None
        reference = (
            request.price
            if request.price is not None
            else entry_price(value, side)
            if value is not None
            else None
        )
        return RiskItem.model_validate(
            {
                "kind": kind,
                "id": identity,
                "symbol": request.symbol,
                "side": side,
                "volume": request.volume,
                "reference_price": reference,
                "stop_loss": request.stop_loss,
                "risk": item_risk(value, side, reference, request.stop_loss, request.volume),
            }
        )
    if request.action == "modify_position":
        position = next((p for p in snapshot.positions if p.id == request.position_id), None)
        if position is None:
            return None
        side = direction(position.side)
        stop = modified_stop(request, position.stop_loss)
        reference = closing_price(value, side) if value is not None and side != "unknown" else None
        return RiskItem.model_validate(
            {
                "kind": kind,
                "id": identity,
                "symbol": position.symbol,
                "side": side,
                "volume": position.volume,
                "reference_price": reference,
                "stop_loss": stop,
                "risk": item_risk(value, side, reference, stop, position.volume),
            }
        )
    if request.action == "modify_order":
        order = next((o for o in snapshot.orders if o.id == request.order_id), None)
        if order is None:
            return None
        side = direction(order.side)
        stop = modified_stop(request, order.stop_loss)
        price = request.price if request.price is not None else order.price
        return RiskItem.model_validate(
            {
                "kind": kind,
                "id": identity,
                "symbol": order.symbol,
                "side": side,
                "volume": order.volume,
                "reference_price": price,
                "stop_loss": stop,
                "risk": item_risk(value, side, price, stop, order.volume),
            }
        )
    return None


def worse(first: Decimal | None, second: Decimal | None) -> Decimal | None:
    if first is None or second is None:
        return None
    return max(first, second)


def visible(row: TradingJournalRow, snapshot: ExecutionSnapshot) -> bool:
    raw = row.result.get("details")
    details = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
    tickets = {
        str(value)
        for value in (
            row.result.get("broker_id"),
            details.get("position_id"),
            details.get("order_id"),
        )
        if value
    }
    return any(
        item.operation_id == row.operation_id or item.id in tickets
        for item in [*snapshot.positions, *snapshot.orders]
    )


def risk_symbols(
    request: TradeRequest | None,
    snapshot: ExecutionSnapshot,
    operations: Iterable[TradingJournalRow],
    *,
    portfolio: bool,
) -> set[str]:
    symbols: set[str] = {request.symbol} if request is not None else set()
    if portfolio:
        symbols |= {item.symbol for item in [*snapshot.positions, *snapshot.orders]}
        symbols |= {
            str(row.request.get("symbol"))
            for row in operations
            if row.request.get("action") in TRADE_LIMIT_ACTIONS
        }
    return symbols


async def read_economics(
    broker: RiskReader, symbols: set[str], snapshot: ExecutionSnapshot
) -> dict[str, Economics]:
    async def one(symbol: str) -> Economics:
        instrument = await broker.instrument(symbol)
        quote = (
            snapshot.quote
            if snapshot.quote is not None and snapshot.quote.symbol == symbol
            else await broker.quote(symbol)
        )
        return economics(instrument, quote)

    ordered = sorted(symbols)
    try:
        async with asyncio.timeout(ECONOMICS_TIMEOUT_SECONDS):
            values = await asyncio.gather(*(one(symbol) for symbol in ordered))
    except LonoraError as error:
        if error.code == "risk_economics_unavailable":
            raise
        raise LonoraError("risk_economics_unavailable", 409) from error
    except Exception as error:
        raise LonoraError("risk_economics_unavailable", 409) from error
    return dict(zip(ordered, values, strict=True))


def deal_pnl(deal: dict[str, Any]) -> Decimal:
    """A deal's contribution to today's P&L; only trade deals may add a gain."""
    kind = str(deal.get("type") or "").strip().upper().removeprefix("DEAL_TYPE_")
    if kind in CASH_FLOW_DEALS:
        return Decimal(0)  # Deposits, withdrawals and broker credit are not trading P&L.
    total = Decimal(0)
    for key in ("profit", "commission", "swap"):
        raw = deal.get(key)
        if raw is None or raw == "":
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation as error:
            raise LonoraError("risk_daily_history_invalid", 409) from error
        if not value.is_finite():
            raise LonoraError("risk_daily_history_invalid", 409)
        total += value
    # A non-trading adjustment counts against the limit, never for it.
    return total if kind in TRADE_DEALS else min(total, Decimal(0))


def trading_day_start(now: datetime, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    local = now.astimezone(zone)
    return datetime.combine(local.date(), time(0), tzinfo=zone)


def daily_loss(
    deals: list[dict[str, Any]],
    positions: list[Position],
    *,
    day_start: datetime,
    timezone: str,
) -> DailyLoss:
    realized = sum((deal_pnl(deal) for deal in deals), Decimal(0))
    unrealized = sum((position.profit for position in positions), Decimal(0))
    return DailyLoss(
        day_start=day_start,
        timezone=timezone,
        realized=realized,
        unrealized=unrealized,
        loss=max(Decimal(0), -(realized + unrealized)),
        deals_counted=len(deals),
    )


async def read_daily_loss(
    broker: RiskReader, snapshot: ExecutionSnapshot, timezone: str, now: datetime
) -> DailyLoss:
    start = trading_day_start(now, timezone)
    try:
        deals = await broker.history(start, now, HISTORY_LIMIT)
    except Exception as error:
        raise LonoraError("risk_daily_history_unavailable", 409) from error
    if len(deals) >= HISTORY_LIMIT:
        # A full page cannot prove that no further loss-making deal exists today.
        raise LonoraError("risk_daily_history_incomplete", 409)
    counted: list[dict[str, Any]] = []
    for deal in deals:
        raw = str(deal.get("time") or "")
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise LonoraError("risk_daily_history_invalid", 409) from error
        if moment.tzinfo is None:
            raise LonoraError("risk_daily_history_invalid", 409)
        if start <= moment <= now:
            counted.append(deal)
    return daily_loss(counted, snapshot.positions, day_start=start, timezone=timezone)


def portfolio_items(
    snapshot: ExecutionSnapshot,
    operations: list[TradingJournalRow],
    values: dict[str, Economics],
) -> dict[tuple[str, str], RiskItem]:
    items: dict[tuple[str, str], RiskItem] = {}
    for position in snapshot.positions:
        items["position", position.id] = position_item(position, values.get(position.symbol))
    for order in snapshot.orders:
        items["order", order.id] = order_item(order, values.get(order.symbol))
    for row in operations:
        request = TradeRequest.model_validate(row.request)
        if request.action in ENTRY_ACTIONS:
            if visible(row, snapshot):
                continue  # Its ticket is already counted from broker state.
            item = requested_item(
                request, snapshot, values, kind="operation", identity=row.operation_id
            )
            if item is not None:
                item.status = row.status
                items["operation", row.operation_id] = item
        elif request.action in MODIFICATIONS:
            key = (
                ("position", str(request.position_id))
                if request.action == "modify_position"
                else ("order", str(request.order_id))
            )
            current = items.get(key)
            requested = requested_item(request, snapshot, values, kind=key[0], identity=key[1])
            if current is not None and requested is not None:
                current.risk = worse(current.risk, requested.risk)
                current.status = "pending_modification:" + row.status
    return items


def total(items: Iterable[RiskItem]) -> Decimal | None:
    amount = Decimal(0)
    for item in items:
        if item.risk is None:
            return None
        amount += item.risk
    return amount


def effective_limit(
    amount: Decimal | None, percent: Decimal | None, equity: Decimal
) -> Decimal | None:
    candidates = [] if amount is None else [amount]
    if percent is not None:
        candidates.append(max(Decimal(0), equity) * percent / Decimal(100))
    return min(candidates) if candidates else None


async def risk_operations(
    session: AsyncSession, owner_id: str, account_id: str, *, exclude: str | None = None
) -> list[TradingJournalRow]:
    """Live operations whose effect may be missing from broker state."""
    query = select(TradingJournalRow).where(
        TradingJournalRow.owner_id == owner_id,
        TradingJournalRow.account_id == account_id,
        or_(
            TradingJournalRow.status.in_(sorted(UNRESOLVED_STATUSES)),
            (TradingJournalRow.status == "confirmed")
            & (
                TradingJournalRow.result["details"]["verification"]["status"].as_string()
                == "pending"
            ),
        ),
    )
    if exclude:
        query = query.where(TradingJournalRow.operation_id != exclude)
    return list(
        await session.scalars(
            query.order_by(TradingJournalRow.submitted_at, TradingJournalRow.operation_id).limit(
                500
            )
        )
    )


async def assess_risk(
    broker: RiskReader,
    request: TradeRequest | None,
    snapshot: ExecutionSnapshot,
    limits: MonetaryRiskLimits,
    *,
    reducing: bool,
    operations: list[TradingJournalRow],
    now: datetime | None = None,
) -> RiskAssessment:
    """Evaluate the owner's limits for ``request`` (or the current book when None)."""
    moment = now or utcnow()
    account = snapshot.account
    base: dict[str, Any] = {
        "currency": account.currency,
        "equity": account.equity,
        "free_margin": account.free_margin,
        "limits": limits,
        "observed_at": moment,
    }
    if request is not None and reducing:
        return RiskAssessment(state="risk_reducing", **base)
    if not limits.configured:
        return RiskAssessment(state="not_configured", **base)
    if limits.currency is not None and limits.currency != account.currency:
        # Never convert or reinterpret an owner amount in another currency.
        return RiskAssessment(state="blocked", reasons=["risk_limit_currency_mismatch"], **base)
    reasons: list[str] = []
    trade_limit = effective_limit(
        limits.max_trade_risk, limits.max_trade_risk_equity_percent, account.equity
    )
    open_limit = effective_limit(
        limits.max_open_risk, limits.max_open_risk_equity_percent, account.equity
    )
    checks_trade = (
        request is not None and trade_limit is not None and request.action in TRADE_LIMIT_ACTIONS
    )
    checks_open = open_limit is not None
    candidate: RiskItem | None = None
    items: dict[tuple[str, str], RiskItem] = {}
    open_risk: Decimal | None = None
    daily: DailyLoss | None = None
    if checks_trade or checks_open:
        try:
            values = await read_economics(
                broker,
                risk_symbols(request, snapshot, operations, portfolio=checks_open),
                snapshot,
            )
            if request is not None:
                candidate = requested_item(
                    request, snapshot, values, kind="candidate", identity=request.operation_id
                )
            if checks_open:
                items = portfolio_items(snapshot, operations, values)
                if candidate is not None and request is not None:
                    # An edit replaces its target's current contribution.
                    if request.action == "modify_position":
                        items.pop(("position", str(request.position_id)), None)
                    elif request.action == "modify_order":
                        items.pop(("order", str(request.order_id)), None)
                    items["candidate", candidate.id] = candidate
                open_risk = total(items.values())
        except LonoraError as error:
            reasons.append(error.code)
        else:
            if checks_trade and candidate is not None and trade_limit is not None:
                if candidate.risk is None:
                    reasons.append("risk_stop_loss_required")
                elif candidate.risk > trade_limit:
                    reasons.append("risk_trade_limit")
            if checks_open:
                if open_risk is None:
                    reasons.append("risk_open_unbounded")
                elif open_risk > open_limit:
                    reasons.append("risk_open_limit")
    if limits.max_daily_loss is not None:
        try:
            daily = await read_daily_loss(broker, snapshot, limits.trading_day_timezone, moment)
        except LonoraError as error:
            reasons.append(error.code)
        else:
            if daily.loss >= limits.max_daily_loss:
                reasons.append("risk_daily_loss_limit")
    if (
        limits.min_free_margin is not None
        and request is not None
        and request.action in ENTRY_ACTIONS
        and account.free_margin < limits.min_free_margin
    ):
        reasons.append("risk_free_margin_floor")
    listed = sorted(
        items.values() if items else [candidate] if candidate is not None else [],
        key=lambda item: (item.kind != "candidate", item.risk is not None, item.id),
    )
    return RiskAssessment(
        state="blocked" if reasons else "within_limits",
        reasons=reasons,
        trade_risk=candidate.risk if candidate is not None else None,
        trade_risk_unbounded=candidate is not None and candidate.risk is None,
        trade_risk_limit=trade_limit,
        open_risk=open_risk,
        open_risk_unbounded=any(item.risk is None for item in items.values()),
        open_risk_limit=open_limit,
        daily=daily,
        items=listed[:MAX_ITEMS],
        **base,
    )
