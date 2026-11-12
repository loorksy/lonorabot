"""Account-wide exact-symbol exposure; deliberately no invented FX conversions."""

from typing import Literal

from lonora_contracts.execution_quality import (
    ExecutionSnapshot,
    ExposureBucket,
    ExposureSnapshot,
)

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
