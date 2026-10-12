from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import EventRow


def event_data(row: EventRow) -> dict[str, Any]:
    return {
        "cursor": row.cursor,
        "kind": row.kind,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "run_id": row.run_id,
        "payload": row.payload,
        "created_at": row.created_at.isoformat(),
    }


async def events_after(
    session: AsyncSession,
    owner_id: str,
    cursor: int,
    thread_id: str | None = None,
    limit: int = 200,
) -> list[EventRow]:
    query = select(EventRow).where(EventRow.owner_id == owner_id, EventRow.cursor > cursor)
    if thread_id:
        query = query.where(EventRow.thread_id == thread_id)
    return list(
        (await session.scalars(query.order_by(EventRow.cursor).limit(min(limit, 500)))).all()
    )


def emit(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    *,
    thread_id: str | None = None,
    agent_id: str | None = None,
    run_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        EventRow(
            owner_id=owner_id,
            kind=kind,
            thread_id=thread_id,
            agent_id=agent_id,
            run_id=run_id,
            payload=payload or {},
        )
    )
