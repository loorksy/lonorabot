"""Scoped admission at the financial boundary: which uncertainty blocks which action.

A request is *risk-reducing* only when, against the fresh broker target read at the
boundary (never the model's or caller's description), it can only shrink the account's
gross exposure or bound its loss:

- ``close_position`` of an existing open position on the same symbol, in full or for at
  most its current volume. Closing is an exit (the owner's "Stop new trading" keeps
  exits allowed). Closing one leg of a hedge reduces gross exposure and modeled loss at
  the stops even though it can raise net directional exposure on the symbol: that is
  deliberate, since flattening a hedged book requires it, and owner-facing texts for
  ``no_risk_increase`` and Emergency Stop say that closing a hedge leg stays allowed.
- ``cancel_order`` of an existing pending order on the same symbol whose fill would not
  reduce the symbol's absolute net position volume: an entry order only adds exposure,
  so removing it reduces risk. A *protective* order — an opposite-side order whose fill
  would offset open positions on the symbol (for example a sell stop below a net long
  book) — bounds the book's loss like a stop-loss does, so cancelling it is removing
  protection and counts as risk-increasing. An order of unknown direction against a
  non-flat book is treated as protective.
- ``modify_position`` that only moves the stop-loss strictly toward the market — higher
  for a buy, lower for a sell — or adds a stop-loss to an unprotected position, while the
  take-profit is unchanged and nothing is cleared.

Everything else is *risk-increasing* for admission: every entry (market or pending), any
pending-order edit, take-profit changes, removing protection (including cancelling a
protective order), widening or keeping a stop, and any request whose target is missing
or does not match.

Global Trading OFF and Emergency Stop stop new risk, not exits: a risk-reducing request
stays admissible on every admission path. This relaxes no authorization — each path has
already passed owner identity, an exact owner approval or a matching signed account grant
— and the before-send preflight, lease fence and broker checks still run.

An unresolved live operation (``submitted`` or ``ambiguous``: possibly sent, outcome not
established) blocks new risk-increasing requests on the same account and symbol, or on the
same position/order ticket, never the whole account, and never a risk-reducing request.
A ``reserved`` operation does not block: under the serialized account send lock it has
provably not crossed the send boundary. The executor persists every final outcome before
it releases that lock, so under the lock another ``submitted`` operation has lost its
sender and blocks; before the lock is taken a ``submitted`` sibling may still be in flight
and about to settle, so only ``ambiguous`` operations reject a request that early (the
locked check at the send boundary repeats with both). A disconnected broker observation
blocks new risk on the account; a ``degraded`` one is decided by the scoped journal check
instead.
"""

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from lonora_contracts.account import Order, Position
from lonora_contracts.trading import UNRESOLVED_STATUSES, TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingJournalRow
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .exposure import direction

# Actions that can be risk-reducing for some broker target; anything else never is.
REDUCING_ACTIONS = frozenset({"close_position", "cancel_order", "modify_position"})
# Recovery observations that do not by themselves prevent new risk. "degraded" lists
# unresolved operations, whose market scope the journal check decides directly.
ADMISSIBLE_RECOVERY = frozenset({"connected", "degraded"})
# Without the account send lock a "submitted" sibling may still be in flight.
LOCK_FREE_BLOCKING = frozenset({"ambiguous"})


def may_reduce_risk(request: TradeRequest) -> bool:
    """Cheap pre-read test; the decision itself needs the current broker target."""
    return request.action in REDUCING_ACTIONS


def net_position_volume(positions: Iterable[Position], symbol: str) -> Decimal | None:
    """Signed open volume on one symbol (long minus short); None if a side is unknown."""
    net = Decimal(0)
    for position in positions:
        if position.symbol != symbol:
            continue
        side = direction(position.side)
        if side == "unknown":
            return None
        net += position.volume if side == "buy" else -position.volume
    return net


def protective_order(order: Order, positions: Iterable[Position]) -> bool:
    """Whether filling this pending order would shrink the symbol's absolute net volume."""
    net = net_position_volume(positions, order.symbol)
    if net == 0:
        return False  # A flat book: any fill only adds exposure.
    side = direction(order.side)
    if net is None or side == "unknown":
        return True  # Cannot prove the order only adds exposure.
    filled = net + (order.volume if side == "buy" else -order.volume)
    return abs(filled) < abs(net)


def risk_reducing(
    request: TradeRequest, target: Position | Order | None, *, positions: Iterable[Position]
) -> bool:
    """Classify against the fresh target and the fresh open positions on the account."""
    if request.action == "close_position":
        return (
            isinstance(target, Position)
            and target.id == request.position_id
            and target.symbol == request.symbol
            and target.volume > 0
            and (request.volume is None or request.volume <= target.volume)
        )
    if request.action == "cancel_order":
        return (
            isinstance(target, Order)
            and target.id == request.order_id
            and target.symbol == request.symbol
            and not protective_order(target, positions)
        )
    if (
        request.action != "modify_position"
        or not isinstance(target, Position)
        or target.id != request.position_id
        or target.symbol != request.symbol
    ):
        return False
    if request.clear_stop_loss or request.clear_take_profit or request.stop_loss is None:
        return False
    if request.take_profit is not None and request.take_profit != target.take_profit:
        return False
    side = direction(target.side)
    if side == "unknown":
        return False
    if not target.stop_loss:
        return True  # Bounding an unprotected position's loss.
    if side == "buy":
        return request.stop_loss > target.stop_loss
    return request.stop_loss < target.stop_loss


async def unresolved_conflict(
    session: AsyncSession,
    owner_id: str,
    request: TradeRequest,
    *,
    statuses: frozenset[str] = UNRESOLVED_STATUSES,
) -> str | None:
    """The oldest unresolved live operation sharing this request's symbol or ticket."""
    return await unresolved_in_scope(
        session,
        owner_id,
        request.account_id,
        request.symbol,
        position_id=request.position_id,
        order_id=request.order_id,
        exclude=request.operation_id,
        statuses=statuses,
    )


async def unresolved_in_scope(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    symbol: str,
    *,
    position_id: str | None = None,
    order_id: str | None = None,
    exclude: str | None = None,
    statuses: frozenset[str] = UNRESOLVED_STATUSES,
) -> str | None:
    scope = [TradingJournalRow.request["symbol"].as_string() == symbol]
    if position_id:
        scope.append(TradingJournalRow.request["position_id"].as_string() == position_id)
    if order_id:
        scope.append(TradingJournalRow.request["order_id"].as_string() == order_id)
    query = select(TradingJournalRow.operation_id).where(
        TradingJournalRow.owner_id == owner_id,
        TradingJournalRow.account_id == account_id,
        TradingJournalRow.execution_mode == "live",
        TradingJournalRow.status.in_(sorted(statuses)),
        or_(*scope),
    )
    if exclude:
        query = query.where(TradingJournalRow.operation_id != exclude)
    return await session.scalar(
        query.order_by(TradingJournalRow.submitted_at, TradingJournalRow.operation_id).limit(1)
    )


async def entry_recovery_status(
    session: AsyncSession,
    owner_id: str,
    account_id: str,
    symbol: str,
    recovery: dict[str, Any] | None,
) -> str | None:
    """The recovery status as it applies to new risk on one market.

    A degraded account observation only blocks the markets that hold unresolved
    operations; elsewhere new risk is evaluated as on a reconciled account.
    """
    status = recovery.get("status") if recovery else None
    if status == "degraded" and not await unresolved_in_scope(
        session, owner_id, account_id, symbol
    ):
        return "connected"
    return status if isinstance(status, str) else None


async def require_operation_scope(
    session: AsyncSession,
    owner_id: str,
    request: TradeRequest,
    *,
    reducing: bool,
    recovery: dict[str, Any] | None,
    send_locked: bool,
) -> None:
    """Reject new risk while relevant broker state is unknown; always admit exits.

    ``send_locked``: the caller holds this account's send lock, so a ``submitted``
    sibling has no live sender and is as unresolved as an ``ambiguous`` one.
    """
    if reducing:
        return
    if recovery and recovery.get("status") not in ADMISSIBLE_RECOVERY:
        raise LonoraError("broker_reconciliation_required", 409)
    statuses = UNRESOLVED_STATUSES if send_locked else LOCK_FREE_BLOCKING
    if await unresolved_conflict(session, owner_id, request, statuses=statuses):
        raise LonoraError("broker_reconciliation_required", 409)
