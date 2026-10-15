"""Compare broker facts, not ticket formats, names, comments or inferred owner intent."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from lonora_contracts.account import Order, Position
from lonora_contracts.broker_activity import BrokerActivity, BrokerRecoverySnapshot
from lonora_db.schema import TradingJournalRow


def material_state(value: Position | Order) -> dict[str, Any]:
    # P&L changes with ticks and is not an owner intervention.
    result = value.model_dump(mode="json", exclude={"profit", "operation_id"})
    for key in ("volume", "open_price", "price", "stop_loss", "take_profit"):
        if result.get(key) is not None:
            result[key] = str(Decimal(str(result[key])).normalize())
    return result


def _known_change(
    previous: Position | Order | None,
    current: Position | Order | None,
    entries: list[TradingJournalRow],
    since: datetime | None,
) -> bool:
    target = current or previous
    assert target is not None
    for entry in entries:
        if entry.status not in {"confirmed", "submitted", "ambiguous"}:
            continue
        request = entry.request
        result = entry.result
        if request.get("symbol") != target.symbol:
            continue
        details = result.get("details", {})
        if previous is None and (
            target.operation_id == entry.operation_id
            or target.id
            in {result.get("broker_id"), details.get("position_id"), details.get("order_id")}
        ):
            return True
        if entry.status != "confirmed":
            continue
        if since is None or entry.updated_at < since:
            continue
        key = "position_id" if isinstance(target, Position) else "order_id"
        if request.get(key) != target.id:
            continue
        action = request.get("action")
        if current is None and action in {"close_position", "cancel_order"}:
            if (
                action == "cancel_order"
                or request.get("volume") is None
                or str(request["volume"]) == str(target.volume)
            ):
                return True
        if (
            current is not None
            and previous is not None
            and action in {"modify_position", "modify_order", "close_position"}
        ):
            expected = material_state(previous)
            if action == "close_position":
                expected["volume"] = str(
                    previous.volume - Decimal(str(request.get("volume") or previous.volume))
                )
            else:
                for field in ("stop_loss", "take_profit"):
                    if request.get("clear_" + field):
                        expected[field] = None
                    elif request.get(field) is not None:
                        expected[field] = request[field]
                if isinstance(current, Order) and request.get("price") is not None:
                    expected["price"] = request["price"]
            # Decimal strings may differ in scale while representing the same broker fact.
            model = Position if isinstance(current, Position) else Order
            if model.model_validate(expected) == current:
                return True
            if material_state(model.model_validate(expected)) == material_state(current):
                return True
    return False


def detect_activity(
    account_id: str,
    previous: BrokerRecoverySnapshot | None,
    positions: list[Position],
    orders: list[Order],
    entries: list[TradingJournalRow],
    *,
    revision: int,
    now: datetime,
) -> list[BrokerActivity]:
    activities: list[BrokerActivity] = []
    for resource, old, new in (
        ("position", previous.positions if previous else [], positions),
        ("order", previous.orders if previous else [], orders),
    ):
        before = {item.id: item for item in old}
        after = {item.id: item for item in new}
        for ticket in sorted(before.keys() | after.keys()):
            left, right = before.get(ticket), after.get(ticket)
            if (
                left is not None
                and right is not None
                and material_state(left) == material_state(right)
            ):
                continue
            item = right or left
            assert item is not None
            change = (
                "discovered"
                if left is None and previous is None
                else "opened"
                if left is None
                else "closed"
                if right is None and resource == "position"
                else "cancelled"
                if right is None
                else "partial_close"
                if right.volume < left.volume
                else "modified"
            )
            identity = str(
                uuid5(
                    NAMESPACE_URL,
                    f"lonora:broker:{account_id}:{revision}:{resource}:{ticket}:{change}",
                )
            )
            activities.append(
                BrokerActivity.model_validate(
                    {
                        "id": identity,
                        "account_id": account_id,
                        "symbol": item.symbol,
                        "ticket": ticket,
                        "resource": resource,
                        "change": change,
                        "origin": "lonora"
                        if _known_change(
                            left, right, entries, previous.observed_at if previous else None
                        )
                        else "external",
                        "observed_at": now,
                        "previous": left,
                        "current": right,
                    }
                )
            )
    return activities
