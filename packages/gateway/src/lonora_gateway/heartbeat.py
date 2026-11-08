from datetime import timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import GatewayRow
from sqlalchemy import delete

# Rows of gateways that stopped long ago are history, not instances.
RETAIN_STOPPED = timedelta(days=7)


async def write_heartbeat(
    db: Database, identity: str, state: str, liveness: dict[str, Any] | None = None
) -> None:
    async with db.sessions() as session, session.begin():
        row = await session.get(GatewayRow, identity)
        if row:
            row.state = state
            row.heartbeat_at = utcnow()
            if liveness is not None:
                row.liveness = liveness
        else:
            session.add(GatewayRow(id=identity, state=state, liveness=liveness or {}))
        await session.execute(
            delete(GatewayRow).where(
                GatewayRow.id != identity, GatewayRow.heartbeat_at < utcnow() - RETAIN_STOPPED
            )
        )
