from pathlib import Path

from lonora_db.client import Database
from lonora_gateway.health import gateway_health

# Refreshed by every heartbeat; the gateway container's healthcheck reads its age
# (infra/compose/docker-compose.prod.yml), relative to the working directory /app.
LIVENESS_FILE = Path(".runtime/gateway-alive")


async def worker_health(db: Database) -> dict[str, object]:
    return await gateway_health(db)
