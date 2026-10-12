from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import GatewayRow


async def write_heartbeat(db: Database, identity: str, state: str) -> None:
    async with db.sessions() as session, session.begin():
        row = await session.get(GatewayRow, identity)
        if row:
            row.state = state
            row.heartbeat_at = utcnow()
        else:
            session.add(GatewayRow(id=identity, state=state))
