from datetime import datetime, timedelta
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_db.attention import raise_system_attention
from lonora_db.client import Database
from lonora_db.gateways import HEARTBEAT_FRESH, gateway_running, last_heartbeat
from lonora_db.owner import get_owner
from lonora_db.runs import aware
from lonora_db.schema import GatewayRow
from lonora_security.secrets import SecretCipher
from sqlalchemy import select

from .push import PushTransport, dispatch_push

# How long no Gateway may run before the owner is told. Longer than a stuck Gateway takes
# to restart itself (lonora_worker.main, 120 s), so a restart that works tells nobody.
STOPPED_AFTER = timedelta(minutes=3)


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


async def tell_owner_if_stopped(
    db: Database,
    since: datetime,
    cipher: SecretCipher,
    transport: PushTransport,
) -> bool:
    """The API's check, from a process that is still running: once no Gateway has run for
    ``STOPPED_AFTER`` (counted from the last heartbeat, and never from before ``since``,
    when the API started), the owner gets one ``gateway_stopped`` item per stop and its
    push (VISION 11.4, Amendment 5). A stopped Gateway cannot push it; while one runs, the
    API sends nothing and the Gateway's own sweep withdraws the item. Returns whether no
    Gateway runs past the grace."""
    now = utcnow()
    async with db.sessions() as session:
        owner = await get_owner(session)
        if owner is None or await gateway_running(session, now):
            return False
        last = await last_heartbeat(session)
    if now - max(last or since, since) < STOPPED_AFTER:
        return False
    async with db.sessions() as session, session.begin():
        # One item per stop, named by the last heartbeat seen before it.
        await raise_system_attention(
            session,
            owner.id,
            "gateway_stopped",
            "gateway:" + (last.isoformat() if last else "never"),
            {"last_heartbeat": last.isoformat() if last else None},
        )
    await dispatch_push(db, owner.id, cipher, transport)
    return True
