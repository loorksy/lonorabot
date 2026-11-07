"""Conclude uncertain management operations from the observed broker target, never a resend.

Modifying protection or a pending price and cancelling an order *set* a target state:
repeating them cannot add exposure, so the target's current state is evidence of whether
the requested change holds. Creates and partial closes change exposure incrementally and
are never inferred this way; their uncertainty stays explicit until correlated broker
evidence or an owner attestation settles it.

Outcomes, all against a fresh broker read and only after the adapter's own correlated
reconciliation was inconclusive:

- modify_position / modify_order, target present: every requested field equals the
  observed value -> ``confirmed`` (``target_state_matches``); otherwise, once the settle
  window after submission has passed -> ``failed`` (``target_state_not_reached``: the
  requested change is not in effect at the broker).
- modify_position / modify_order, target gone -> ``resolved`` (the position was closed or
  the order is no longer pending; the change can no longer affect the account).
- cancel_order, order still pending after the settle window -> ``failed``
  (``target_state_not_reached``); order gone with no fill evidence after the settle
  window -> ``confirmed`` (``order_no_longer_pending``); fully filled before the cancel ->
  ``failed`` (``order_filled_before_cancel``); a partial fill stays uncertain.
- close_position in full: position gone -> ``confirmed`` (``position_no_longer_open``);
  still open after the settle window -> ``failed`` (``target_state_not_reached``).
  A partial close whose position is gone -> ``resolved``; otherwise it stays uncertain.
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


def _resolved(operation_id: str, basis: str, observed_at: datetime) -> TradeResult:
    # The target can no longer be affected; whether this operation applied is not known.
    return _receipt(
        operation_id,
        "resolved",
        basis,
        observed_at,
        resolution={"source": "broker_state", "basis": basis},
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
            if request.volume is None:
                return _receipt(operation_id, "confirmed", "position_no_longer_open", observed_at)
            return _resolved(operation_id, "target_closed", observed_at)
        if request.volume is None and settled:
            return _receipt(
                operation_id,
                "failed",
                "target_state_not_reached",
                observed_at,
                observed_target=position.model_dump(mode="json"),
            )
        return None
    if request.action == "cancel_order":
        order = next((o for o in orders if o.id == request.order_id), None)
        if order is not None:
            if not settled:
                return None
            return _receipt(
                operation_id,
                "failed",
                "target_state_not_reached",
                observed_at,
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
        return _receipt(operation_id, "confirmed", "order_no_longer_pending", observed_at)
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
    observed = {name: _observed(target, name) for name in wanted}
    if wanted and all(observed[name] == value for name, value in wanted.items()):
        return _receipt(
            operation_id,
            "confirmed",
            "target_state_matches",
            observed_at,
            observed_target=target.model_dump(mode="json"),
        )
    if not settled:
        return None
    return _receipt(
        operation_id,
        "failed",
        "target_state_not_reached",
        observed_at,
        observed_target=target.model_dump(mode="json"),
    )
