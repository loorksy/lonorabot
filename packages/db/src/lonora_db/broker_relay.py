"""The broker relay: MetaApi requests the API process hands to the Gateway.

Only the Gateway keeps MetaApi connections, so each account has exactly one subscription
and one synchronization owner across processes. The API process writes a request row and
polls for its answer; the Gateway claims each pending row once, answers it with its own
adapter, and never claims it again. A request nobody claimed before the asker gave up is
cancelled, atomically against the claim, so it is never served late.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from lonora_contracts.domain import new_id, utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import delete, select, update

from .client import Database
from .schema import BrokerRelayRow

POLL_SECONDS = 0.1
CLAIM_LIMIT = 16
KEEP_ANSWERS = timedelta(hours=1)
# No asker waits longer. An older pending request is never served: its asker is gone (an
# order is never placed long after the owner's request).
MAX_WAIT = timedelta(seconds=60)


@dataclass(frozen=True)
class RelayRequest:
    id: str
    owner_id: str
    connection_id: str
    kind: str
    arguments: dict[str, Any]


async def ask(
    db: Database,
    owner_id: str,
    connection_id: str,
    kind: str,
    arguments: dict[str, Any],
    wait_seconds: float,
) -> Any:
    """The Gateway's answer, or its error re-raised. ``broker_gateway_unavailable`` when no
    Gateway took the request (nothing was done); ``broker_gateway_no_answer`` when it took
    it and did not answer in time (it may still be done: an order is in the journal)."""
    wait_seconds = min(wait_seconds, MAX_WAIT.total_seconds())
    request_id = new_id()
    async with db.sessions() as session, session.begin():
        session.add(
            BrokerRelayRow(
                id=request_id,
                owner_id=owner_id,
                connection_id=connection_id,
                kind=kind,
                arguments=arguments,
                state="pending",
                created_at=utcnow(),
            )
        )
    loop = asyncio.get_running_loop()
    deadline = loop.time() + wait_seconds
    answered, code, status, result = False, None, None, None
    try:
        while True:
            await asyncio.sleep(POLL_SECONDS)
            async with db.sessions() as session:
                row = await session.get(BrokerRelayRow, request_id)
                if row is not None and row.state == "answered":
                    answered = True
                    code, status, result = row.error_code, row.error_status, row.result
            if answered or loop.time() >= deadline:
                break
    except asyncio.CancelledError:
        await asyncio.shield(_withdraw(db, request_id))
        raise
    if not answered:
        if await _withdraw(db, request_id):
            raise LonoraError("broker_gateway_unavailable", 503)
        raise LonoraError("broker_gateway_no_answer", 504)
    async with db.sessions() as session, session.begin():
        await session.execute(delete(BrokerRelayRow).where(BrokerRelayRow.id == request_id))
    if code:
        raise LonoraError(code, status or 502)
    return result


async def _withdraw(db: Database, request_id: str) -> bool:
    """Cancel a request no Gateway claimed yet; False when one already did."""
    async with db.sessions() as session, session.begin():
        cancelled = (
            await session.execute(
                update(BrokerRelayRow)
                .where(BrokerRelayRow.id == request_id, BrokerRelayRow.state == "pending")
                .values(state="cancelled")
                .returning(BrokerRelayRow.id)
            )
        ).first()
    return cancelled is not None


async def claim(db: Database) -> list[RelayRequest]:
    """Pending requests still awaited, each claimed exactly once."""
    async with db.sessions() as session, session.begin():
        rows = list(
            await session.scalars(
                select(BrokerRelayRow)
                .where(
                    BrokerRelayRow.state == "pending",
                    BrokerRelayRow.created_at > utcnow() - MAX_WAIT,
                )
                .order_by(BrokerRelayRow.created_at)
                .limit(CLAIM_LIMIT)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            row.state = "claimed"
        return [
            RelayRequest(row.id, row.owner_id, row.connection_id, row.kind, dict(row.arguments))
            for row in rows
        ]


async def answer(
    db: Database, request_id: str, result: Any = None, error: LonoraError | None = None
) -> None:
    async with db.sessions() as session, session.begin():
        await session.execute(
            update(BrokerRelayRow)
            .where(BrokerRelayRow.id == request_id, BrokerRelayRow.state == "claimed")
            .values(
                state="answered",
                result=None if error else result,
                error_code=error.code if error else None,
                error_status=error.status if error else None,
            )
        )


async def prune(db: Database) -> None:
    """Rows whose asker is long gone: answered late, cancelled, or abandoned."""
    async with db.sessions() as session, session.begin():
        await session.execute(
            delete(BrokerRelayRow).where(BrokerRelayRow.created_at < utcnow() - KEEP_ANSWERS)
        )
