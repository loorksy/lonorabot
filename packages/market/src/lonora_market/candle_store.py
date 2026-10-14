"""Merge official broker bars under the same account fence as quotes."""

from datetime import UTC, datetime
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.market_snapshots import save_snapshot, snapshot_id
from lonora_db.schema import MarketSnapshotRow
from sqlalchemy.ext.asyncio import AsyncSession


async def merge_candle(
    session: AsyncSession,
    owner_id: str,
    connection_id: str,
    candle: Candle,
    version: int,
    identity: str,
) -> bool:
    await BrokerSessionRepository().get(session, owner_id, connection_id, lock=True)
    row = await session.get(
        MarketSnapshotRow,
        snapshot_id(owner_id, connection_id, candle.symbol, candle.timeframe),
        with_for_update=True,
    )
    payload: dict[str, Any] = dict(row.payload) if row and row.connection_version == version else {}
    bars = {value["time"]: value for value in payload.get("candles", [])}
    value = candle.model_copy(update={"time": candle.time.astimezone(UTC)}).model_dump(mode="json")
    previous = bars.get(value["time"])
    if previous == value:
        return False
    bars[value["time"]] = value
    values = sorted(bars.values(), key=lambda bar: datetime.fromisoformat(bar["time"]))[-1000:]
    updates = {
        key: value
        for key, value in payload.get("stream_bar_updates", {}).items()
        if key in {bar["time"] for bar in values}
    }
    updates[value["time"]] = utcnow().isoformat()
    return await save_snapshot(
        session,
        owner_id,
        connection_id,
        candle.symbol,
        candle.timeframe,
        {
            **payload,
            "candles": values,
            "limit": payload.get("limit", 0),
            "stream_updated_at": utcnow().isoformat(),
            "stream_bar_time": value["time"],
            "stream_bar_updates": updates,
        },
        version,
        identity,
    )


async def merge_history(
    session: AsyncSession,
    owner_id: str,
    connection_id: str,
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    limit: int,
    version: int,
    requested_at: datetime,
) -> list[Candle]:
    await BrokerSessionRepository().get(session, owner_id, connection_id, lock=True)
    row = await session.get(
        MarketSnapshotRow,
        snapshot_id(owner_id, connection_id, symbol, timeframe),
        with_for_update=True,
    )
    previous = dict(row.payload) if row and row.connection_version == version else {}
    values = {
        value.time.astimezone(UTC).isoformat().replace("+00:00", "Z"): value.model_copy(
            update={"time": value.time.astimezone(UTC)}
        ).model_dump(mode="json")
        for value in candles
    }
    existing = previous.get("candles", [])
    # Historical reads reconcile completed bars. Preserve the newest official
    # streamed bar, which historical endpoints commonly deliver one packet behind.
    if previous.get("stream_updated_at") and existing:
        latest = max(existing, key=lambda value: datetime.fromisoformat(value["time"]))
        if not values or datetime.fromisoformat(latest["time"]) >= max(
            datetime.fromisoformat(key) for key in values
        ):
            values[latest["time"]] = latest
    for value in existing:
        updated = previous.get("stream_bar_updates", {}).get(value["time"])
        if updated and datetime.fromisoformat(updated) >= requested_at:
            values[value["time"]] = value
    merged = sorted(values.values(), key=lambda value: datetime.fromisoformat(value["time"]))[
        -max(limit, 1) :
    ]
    await save_snapshot(
        session,
        owner_id,
        connection_id,
        symbol,
        timeframe,
        {
            **previous,
            "candles": merged,
            "limit": limit,
            "history_updated_at": utcnow().isoformat(),
        },
        version,
    )
    return [Candle.model_validate(value) for value in merged]
