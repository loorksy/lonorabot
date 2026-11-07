"""Conclude uncertain management operations from the observed broker target, never a resend.

Modifying protection or a pending price and cancelling an order *set* a target state:
repeating them cannot add exposure, so the target's current state is evidence of whether
the requested change holds. Creates and partial closes change exposure incrementally and
are never inferred this way; their uncertainty stays explicit until correlated broker
evidence or an owner attestation settles it.

Three facts are compared: the request, the target as the send boundary observed it
(``before``, server-captured evidence) and the target now. Only these conclusions are
drawn, all against a fresh broker read and only after the adapter's own correlated
reconciliation was inconclusive:

- ``confirmed`` means the *requested end state holds* at the broker
  (``details.conclusion == "requested_end_state_observed"``). It does not claim that this
  operation's own request, rather than another change, produced it.
- ``failed`` (``target_state_not_reached``) is concluded only after the settle window and
  only when every requested field (or the volume, for a close) still equals the
  before-send target: nothing changed, so the requested change did not take effect.
- ``resolved`` settles the uncertainty without an outcome claim: the target is gone
  (``target_closed`` / ``target_no_longer_pending``), or after the settle window it
  differs from both the request and the before-send state (``target_changed``: a partial
  fill, a later admitted change or a manual edit superseded it). Either way the current
  state is observed and this operation can no longer change it.

Per action:

- modify_position / modify_order: requested fields observed -> ``confirmed``
  (``target_state_matches``); unchanged since before send -> ``failed``; changed
  otherwise -> ``resolved`` (``target_changed``); target gone -> ``resolved``.
- cancel_order: order gone with no fill evidence after the settle window -> ``confirmed``
  (``order_no_longer_pending``); still pending after the settle window -> ``failed``
  (a cancel cannot partly apply); fully filled before the cancel -> ``failed``
  (``order_filled_before_cancel``); a partial fill stays uncertain.
- close_position: position gone -> ``resolved`` (``target_closed``), because a stop,
  take-profit, manual or other close leaves the same state and a close receipt would
  imply this operation's exit price. A full close whose position still has its
  before-send volume after the settle window -> ``failed``; a different volume ->
  ``resolved`` (``target_changed``). A partial close with its position still open stays
  uncertain.
- Without before-send evidence nothing proves the target unchanged: no ``failed`` and no
  ``target_changed`` conclusion is drawn.
"""

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from lonora_contracts.account import Order, Position
from lonora_contracts.trading import TradeRequest, TradeResult

# A request still queued at the broker may apply shortly after a lost response. Only an
# observation made this long after the send boundary may conclude that it did not.
SETTLE_WINDOW = timedelta(minutes=2)
TARGET_STATE_ACTIONS = frozenset(
    {"modify_position", "modify_order", "cancel_order", "close_position"}
)


def _wanted(request: TradeRequest) -> dict[str, Decimal | None]:
    wanted: dict[str, Decimal | None] = {}
    for name in ("stop_loss", "take_profit"):
        if getattr(request, "clear_" + name):
            wanted[name] = None
        elif getattr(request, name) is not None:
            wanted[name] = getattr(request, name)
    if request.action == "modify_order" and request.price is not None:
        wanted["price"] = request.price
    return wanted


def _observed(target: Position | Order, name: str) -> Decimal | None:
    value = getattr(target, name, None)
    return value or None  # Brokers report an absent stop as 0.


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except (InvalidOperation, ValueError):
        return None


def _same_target(
    before: Position | Order | None, target: Position | Order
) -> Position | Order | None:
    """The before-send observation of this very target, if the evidence holds one."""
    if (
        before is None
        or before.id != target.id
        or isinstance(before, Position) != isinstance(target, Position)
    ):
        return None
    return before


def _receipt(
    operation_id: str,
    status: str,
    code: str,
    observed_at: datetime,
    **evidence: Any,
) -> TradeResult:
    return TradeResult.model_validate(
        {
            "operation_id": operation_id,
            "status": status,
            "code": code,
            "details": {
                "reconciled": True,
                "evidence": "broker_target_state",
                "observed_at": observed_at.isoformat(),
                **evidence,
            },
        }
    )


def _matched(operation_id: str, code: str, observed_at: datetime, **evidence: Any) -> TradeResult:
    return _receipt(
        operation_id,
        "confirmed",
        code,
        observed_at,
        conclusion="requested_end_state_observed",
        **evidence,
    )


def _not_reached(
    operation_id: str, observed_at: datetime, target: Position | Order, before: Position | Order
) -> TradeResult:
    return _receipt(
        operation_id,
        "failed",
        "target_state_not_reached",
        observed_at,
        conclusion="before_send_state_unchanged",
        observed_target=target.model_dump(mode="json"),
        before_send_target=before.model_dump(mode="json"),
    )


def _resolved(
    operation_id: str,
    basis: str,
    observed_at: datetime,
    *,
    target: Position | Order | None = None,
    before: Position | Order | None = None,
) -> TradeResult:
    # The target can no longer be affected; whether this operation applied is not known.
    evidence: dict[str, Any] = {}
    if target is not None:
        evidence["observed_target"] = target.model_dump(mode="json")
    if before is not None:
        evidence["before_send_target"] = before.model_dump(mode="json")
    return _receipt(
        operation_id,
        "resolved",
        basis,
        observed_at,
        resolution={"source": "broker_state", "basis": basis},
        **evidence,
    )


def target_state_receipt(
    operation_id: str,
    request: TradeRequest,
    positions: list[Position],
    orders: list[Order],
    *,
    submitted_at: datetime | None,
    observed_at: datetime,
    deals: list[dict[str, Any]] | None = None,
    before: Position | Order | None = None,
) -> TradeResult | None:
    """A conclusive receipt from current broker state, or None to keep the uncertainty."""
    if request.action not in TARGET_STATE_ACTIONS:
        return None
    settled = submitted_at is not None and observed_at >= submitted_at + SETTLE_WINDOW
    if request.action == "close_position":
        position = next((p for p in positions if p.id == request.position_id), None)
        if position is None:
            return _resolved(operation_id, "target_closed", observed_at)
        prior = _same_target(before, position)
        if request.volume is not None or not settled or prior is None:
            return None
        if position.volume == prior.volume:
            return _not_reached(operation_id, observed_at, position, prior)
        # Part of the position was closed (possibly by this request) or it was changed.
        return _resolved(operation_id, "target_changed", observed_at, target=position, before=prior)
    if request.action == "cancel_order":
        order = next((o for o in orders if o.id == request.order_id), None)
        if order is not None:
            if not settled:
                return None
            # A cancel removes the whole order or nothing: an order still pending after
            # the settle window means this cancel did not take effect.
            return _receipt(
                operation_id,
                "failed",
                "target_state_not_reached",
                observed_at,
                conclusion="order_still_pending",
                observed_target=order.model_dump(mode="json"),
            )
        if deals is None:
            return None  # Without fill history an absent order may have become exposure.
        filled = sum(
            (
                _decimal(deal.get("volume")) or Decimal(0)
                for deal in deals
                if str(deal.get("orderId") or "") == request.order_id
            ),
            Decimal(0),
        )
        # An MT position opened by a pending order carries that order's ticket.
        opened = any(p.id == request.order_id for p in positions)
        if filled > 0 or opened:
            if isinstance(before, Order) and filled >= before.volume:
                return _receipt(
                    operation_id,
                    "failed",
                    "order_filled_before_cancel",
                    observed_at,
                    filled_volume=str(filled),
                )
            return None  # A partial fill and cancel interplay needs richer evidence.
        if not settled:
            return None
        return _matched(operation_id, "order_no_longer_pending", observed_at)
    target: Position | Order | None = (
        next((p for p in positions if p.id == request.position_id), None)
        if request.action == "modify_position"
        else next((o for o in orders if o.id == request.order_id), None)
    )
    if target is None:
        return _resolved(
            operation_id,
            "target_closed" if request.action == "modify_position" else "target_no_longer_pending",
            observed_at,
        )
    if target.symbol != request.symbol:
        return None
    wanted = _wanted(request)
    if not wanted:
        return None
    observed = {name: _observed(target, name) for name in wanted}
    if all(observed[name] == value for name, value in wanted.items()):
        return _matched(
            operation_id,
            "target_state_matches",
            observed_at,
            observed_target=target.model_dump(mode="json"),
        )
    prior = _same_target(before, target)
    if not settled or prior is None:
        return None
    if all(observed[name] == _observed(prior, name) for name in wanted):
        return _not_reached(operation_id, observed_at, target, prior)
    # Neither requested nor the pre-send state: superseded by another change.
    return _resolved(operation_id, "target_changed", observed_at, target=target, before=prior)
