"""The broker relay: MetaApi requests the API process hands to the Gateway.

Only the Gateway keeps MetaApi connections, so each account has exactly one subscription
and one synchronization owner across processes. The API process writes a request row and
polls for its answer; the Gateway claims each pending row once, answers it with its own
adapter, and never claims it again. A request nobody claimed within its claim window is
withdrawn, atomically against the claim, so it is never served late. Every age is the
database's own clock.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from lonora_contracts.domain import new_id
from lonora_core.user_error import LonoraError
from sqlalchemy import case, delete, func, or_, select, text, update

from .client import Database
from .schema import BrokerRelayRow

log = logging.getLogger(__name__)
POLL_SECONDS = 0.1
KEEP_ANSWERS_SECONDS = 3600
# How long after it was written a request may still be claimed. An owner's order is
# claimed at once or never: it is never placed long after the owner asked. The asker
# withdraws a request still unclaimed at its window and answers that nothing was done.
CLAIM_SECONDS = {"execute": 5.0}
READ_CLAIM_SECONDS = 30.0


def seconds(value: float) -> Any:
    return text(f"interval '{float(value)} seconds'")


def claim_seconds(kind: str) -> float:
    return CLAIM_SECONDS.get(kind, READ_CLAIM_SECONDS)


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
    it and did not answer in time, or failed unexpectedly while executing an order (it may
    still be done: an order that was reserved is in the journal)."""
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
                created_at=func.now(),
            )
        )
    loop = asyncio.get_running_loop()
    started = loop.time()
    claim_by, deadline = started + claim_seconds(kind), started + wait_seconds
    row_state, code, status, details, result = "pending", None, None, None, None
    try:
        while True:
            await asyncio.sleep(POLL_SECONDS)
            async with db.sessions() as session:
                row = await session.get(BrokerRelayRow, request_id)
                if row is not None:
                    row_state = row.state
                    code, status = row.error_code, row.error_status
                    details, result = row.error_details, row.result
            now = loop.time()
            if (
                row_state == "answered"
                or now >= deadline
                or (row_state == "pending" and now >= claim_by)
            ):
                break
    except asyncio.CancelledError:
        await asyncio.shield(_withdraw(db, request_id))
        raise
    if row_state != "answered":
        if await _withdraw(db, request_id):
            raise LonoraError("broker_gateway_unavailable", 503)
        raise LonoraError("broker_gateway_no_answer", 504)
    try:
        async with db.sessions() as session, session.begin():
            await session.execute(delete(BrokerRelayRow).where(BrokerRelayRow.id == request_id))
    except Exception as error:  # noqa: BLE001 - the answer stands; prune removes the row
        log.warning("broker_relay_cleanup_failed type=%s", type(error).__name__)
    if code:
        failure = LonoraError(code, status or 502)
        if details and "retry_until" in details:
            failure.retry_until = details["retry_until"]  # pyright: ignore[reportAttributeAccessIssue]
        raise failure
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


async def claim(db: Database, limit: int) -> list[RelayRequest]:
    """Pending requests still inside their claim window, each claimed exactly once."""
    if limit <= 0:
        return []
    async with db.sessions() as session, session.begin():
        rows = list(
            await session.scalars(
                select(BrokerRelayRow)
                .where(
                    BrokerRelayRow.state == "pending",
                    BrokerRelayRow.created_at > func.now() - seconds(READ_CLAIM_SECONDS),
                    or_(
                        BrokerRelayRow.kind != "execute",
                        BrokerRelayRow.created_at > func.now() - seconds(CLAIM_SECONDS["execute"]),
                    ),
                )
                # Owners' orders first: slow reads never push one past its window.
                .order_by(
                    case((BrokerRelayRow.kind == "execute", 0), else_=1),
                    BrokerRelayRow.created_at,
                )
                .limit(limit)
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
    retry_until = getattr(error, "retry_until", None)
    async with db.sessions() as session, session.begin():
        await session.execute(
            update(BrokerRelayRow)
            .where(BrokerRelayRow.id == request_id, BrokerRelayRow.state == "claimed")
            .values(
                state="answered",
                result=None if error else result,
                error_code=error.code if error else None,
                error_status=error.status if error else None,
                error_details={"retry_until": retry_until}
                if isinstance(retry_until, (int, float))
                else None,
            )
        )


async def prune(db: Database) -> None:
    """Rows whose asker is long gone: answered late, cancelled, or abandoned."""
    async with db.sessions() as session, session.begin():
        await session.execute(
            delete(BrokerRelayRow).where(
                BrokerRelayRow.created_at < func.now() - seconds(KEEP_ANSWERS_SECONDS)
            )
        )
