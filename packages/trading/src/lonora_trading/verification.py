"""Observe a confirmed mutation separately; never send or retry a financial effect."""

import asyncio
from decimal import Decimal
from typing import Any

from lonora_adapter_kit.broker import BrokerStateReader
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionSnapshot
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError


async def verify_effect(
    broker: BrokerStateReader,
    request: TradeRequest,
    receipt: TradeResult,
    before: ExecutionSnapshot | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "pending",
        "source": "broker_state_read",
        "observed_at": utcnow().isoformat(),
        "financial_retry_allowed": False,
    }
    if receipt.status != "confirmed" or before is None:
        return {**result, "code": "confirmed_receipt_required"}
    try:
        async with asyncio.timeout(10):
            positions, orders = await asyncio.gather(broker.positions(), broker.orders())
        if len(positions) > 1000 or len(orders) > 1000:
            return {**result, "code": "broker_snapshot_limit"}
    except Exception as error:
        return {
            **result,
            "code": error.code if isinstance(error, LonoraError) else "verification_unavailable",
        }
    result["observed_at"] = utcnow().isoformat()
    position = next((p for p in positions if p.id == request.position_id), None)
    order = next((o for o in orders if o.id == request.order_id), None)
    previous_position = next((p for p in before.positions if p.id == request.position_id), None)
    previous_order = next((o for o in before.orders if o.id == request.order_id), None)
    matched = False
    observed = None
    if request.action in {"buy", "sell"}:
        target_id = str(receipt.details.get("position_id") or receipt.broker_id or "")
        observed = next(
            (p for p in positions if p.id == target_id and p.symbol == request.symbol), None
        )
        # Do not confuse an order ticket with an unrelated position or a netting
        # account's pre-existing total. Missing exact evidence stays pending.
        prior = next((p for p in before.positions if p.id == target_id), None)
        matched = bool(
            observed
            and observed.side == request.action
            and request.volume is not None
            and not receipt.details.get("partial_execution")
            and observed.volume == request.volume + (prior.volume if prior else Decimal(0))
        )
    elif request.action in {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}:
        target_id = str(receipt.details.get("order_id") or receipt.broker_id or "")
        observed = next((o for o in orders if o.id == target_id), None)
        matched = bool(
            observed
            and observed.symbol == request.symbol
            and observed.side == request.action
            and observed.volume == request.volume
            and observed.price == request.price
        )
    elif request.action == "cancel_order":
        matched = bool(previous_order and previous_order.symbol == request.symbol and order is None)
    elif request.action == "close_position" and previous_position:
        closing = request.volume or previous_position.volume
        expected = previous_position.volume - closing
        matched = bool(
            previous_position.symbol == request.symbol
            and not receipt.details.get("partial_execution")
            and (
                (expected == 0 and position is None)
                or (expected > 0 and position and position.volume == expected)
            )
        )
        observed = position
    elif request.action in {"modify_position", "modify_order"}:
        observed = position if request.action == "modify_position" else order
        previous = previous_position if request.action == "modify_position" else previous_order
        matched = bool(observed and previous and observed.symbol == request.symbol)
        for name in ("stop_loss", "take_profit"):
            wanted = (
                None
                if getattr(request, "clear_" + name)
                else getattr(request, name)
                if getattr(request, name) is not None
                else getattr(previous, name, None)
            )
            matched = matched and (getattr(observed, name, None) or None) == (wanted or None)
        if request.action == "modify_order" and request.price is not None:
            matched = matched and bool(order and order.price == request.price)
    if observed:
        if request.action in {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}:
            for name in ("stop_loss", "take_profit"):
                if getattr(request, name) is not None:
                    matched = matched and getattr(observed, name, None) == getattr(request, name)
        if request.action in {"modify_position", "modify_order"}:
            prior_target = (
                previous_position if request.action == "modify_position" else previous_order
            )
            matched = matched and bool(prior_target and observed.volume == prior_target.volume)
        result["observed_target"] = observed.model_dump(mode="json")
    return {
        **result,
        "status": "verified" if matched else "pending",
        "code": "broker_state_matches" if matched else "broker_state_not_yet_verified",
    }
