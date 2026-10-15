"""Account-wide exact-symbol exposure; deliberately no invented FX conversions."""

from typing import Literal

from lonora_contracts.execution_quality import (
    ExecutionPolicy,
    ExecutionSnapshot,
    ExposureBucket,
    ExposureSnapshot,
)
from lonora_contracts.trading import TradeRequest

ENTRY_ACTIONS = {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}


def direction(side: str) -> Literal["buy", "sell", "unknown"]:
    side = side.removeprefix("ORDER_TYPE_").casefold()
    return "buy" if side.startswith("buy") else "sell" if side.startswith("sell") else "unknown"


def account_exposure(snapshot: ExecutionSnapshot) -> ExposureSnapshot:
    buckets: dict[tuple[str, str], ExposureBucket] = {}
    for position in snapshot.positions:
        side = direction(position.side)
        key = position.symbol, side
        bucket = buckets.setdefault(
            key,
            ExposureBucket(symbol=position.symbol, direction=side),
        )
        bucket.position_volume += position.volume
        bucket.positions += 1
        bucket.unprotected_positions += int(position.stop_loss is None)
    for order in snapshot.orders:
        side = direction(order.side)
        key = order.symbol, side
        bucket = buckets.setdefault(
            key,
            ExposureBucket(symbol=order.symbol, direction=side),
        )
        bucket.pending_volume += order.volume
        bucket.orders += 1
    return ExposureSnapshot(
        account_id=snapshot.account.id,
        observed_at=snapshot.observed_at,
        currency=snapshot.account.currency,
        equity=snapshot.account.equity,
        margin=snapshot.account.margin,
        free_margin=snapshot.account.free_margin,
        buckets=[buckets[key] for key in sorted(buckets)],
    )


def exposure_reasons(
    snapshot: ExecutionSnapshot, request: TradeRequest, policy: ExecutionPolicy
) -> list[str]:
    if request.action not in ENTRY_ACTIONS:
        return []  # Risk-reducing actions must not be blocked by an entry limit.
    reasons: list[str] = []
    market = request.action in {"buy", "sell"}
    if (
        market
        and policy.max_positions is not None
        and len(snapshot.positions) >= policy.max_positions
    ):
        reasons.append("portfolio_position_limit")
    if (
        not market
        and policy.max_pending_orders is not None
        and len(snapshot.orders) >= policy.max_pending_orders
    ):
        reasons.append("portfolio_pending_order_limit")
    if policy.max_symbol_direction_volume is not None:
        bucket = next(
            (
                item
                for item in account_exposure(snapshot).buckets
                if item.symbol == request.symbol and item.direction == direction(request.action)
            ),
            None,
        )
        existing = bucket.position_volume + bucket.pending_volume if bucket else 0
        if existing + (request.volume or 0) > policy.max_symbol_direction_volume:
            reasons.append("portfolio_direction_volume_limit")
    return reasons
