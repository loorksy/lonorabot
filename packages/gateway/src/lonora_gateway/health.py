from datetime import timedelta
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.runs import aware
from lonora_db.schema import GatewayRow
from sqlalchemy import select

HEARTBEAT_FRESH = timedelta(seconds=45)


def stalled_steps(liveness: dict[str, Any]) -> list[str]:
    steps = cast(dict[str, dict[str, Any]], liveness.get("steps") or {})
    return sorted(
        name for name, step in steps.items() if step.get("critical") and step.get("stalled")
    )


async def gateway_health(db: Database) -> dict[str, object]:
    """Ready only while a gateway's heartbeat is fresh and none of its critical steps stalled.

    The heartbeat is its own step, so a stuck reconciliation or a broken routine can no
    longer hide behind a heartbeat written by the loop it blocked.
    """
    async with db.sessions() as session:
        rows = (await session.scalars(select(GatewayRow))).all()
    now = utcnow()
    ready: list[str] = []
    degraded: dict[str, list[str]] = {}
    for row in rows:
        if (
            row.state not in {"running", "ready"}
            or now - aware(row.heartbeat_at) >= HEARTBEAT_FRESH
        ):
            continue
        stalled = stalled_steps(row.liveness or {})
        if stalled:
            degraded[row.id] = stalled
        else:
            ready.append(row.id)
    return {"ready": bool(ready), "instances": ready, "stalled": degraded}
