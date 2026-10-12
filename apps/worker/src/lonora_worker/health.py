from lonora_db.client import Database
from lonora_gateway.health import gateway_health


async def worker_health(db: Database) -> dict[str, object]:
    return await gateway_health(db)
