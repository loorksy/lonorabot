from datetime import timedelta

from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.runs import aware
from lonora_db.schema import GatewayRow
from sqlalchemy import select


async def gateway_health(db: Database) -> dict[str, object]:
    async with db.sessions() as session:
        rows = (await session.scalars(select(GatewayRow))).all()
        ready = [
            row.id
            for row in rows
            if row.state in {"running", "ready"}
            and utcnow() - aware(row.heartbeat_at) < timedelta(seconds=45)
        ]
        return {"ready": bool(ready), "instances": ready}
