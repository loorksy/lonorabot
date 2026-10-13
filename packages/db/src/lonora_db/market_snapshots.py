from datetime import datetime
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import stable_id
from sqlalchemy.ext.asyncio import AsyncSession

from lonora_db.broker_sessions import BrokerSessionRepository

from .schema import MarketSnapshotRow


def snapshot_id(owner_id: str, connection_id: str, symbol: str, timeframe: str) -> str:
    return stable_id(owner_id, connection_id + ":" + symbol + ":" + timeframe)


async def save_snapshot(
    session: AsyncSession,
    owner_id: str,
    connection_id: str,
    symbol: str,
    timeframe: str,
    payload: dict[str, Any],
    expected_version: int | None = None,
    stream_owner: str | None = None,
) -> bool:
    # Serialize missing-row creation against the owning broker connection and deletion.
    connection = await BrokerSessionRepository().get(session, owner_id, connection_id, lock=True)
    if not connection.payload.get("enabled") or (
        expected_version is not None and connection.version != expected_version
    ):
        raise LonoraError("broker_configuration_changed", 409)
    if stream_owner and (
        connection.state.get("market_stream_owner") != stream_owner
        or not connection.state.get("market_stream_until")
        or datetime.fromisoformat(connection.state["market_stream_until"]) <= utcnow()
    ):
        raise LonoraError("market_stream_lease_lost", 409)
    key = snapshot_id(owner_id, connection_id, symbol, timeframe)
    row = await session.get(MarketSnapshotRow, key, with_for_update=True)
    if row is None:
        session.add(
            MarketSnapshotRow(
                id=key,
                owner_id=owner_id,
                connection_id=connection_id,
                symbol=symbol,
                timeframe=timeframe,
                payload=payload,
                connection_version=connection.version,
            )
        )
    else:
        # Delayed stream packets must not overwrite a newer quote.
        if (
            not timeframe
            and row.connection_version == connection.version
            and datetime.fromisoformat(row.payload["observed_at"])
            > datetime.fromisoformat(payload["observed_at"])
        ):
            return False
        row.connection_version = connection.version
        row.payload = payload
        row.updated_at = utcnow()
    return True
