import time
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import EventRow, SettingRow

PUBLIC_CURSOR = "_ln_public_cursor"


async def publish_committed(session: AsyncSession, force: bool = False) -> None:
    """Assign delivery order after producers commit, so a late commit cannot fall behind a cursor."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(1524053101)"))
    counter = await session.get(SettingRow, "event_publication", with_for_update=True)
    maximum = int((await session.scalar(select(func.max(EventRow.cursor)))) or 0)
    if counter is None:
        counter = SettingRow(key="event_publication", payload={"last": maximum})
        session.add(counter)
        await session.flush()
    state = dict(counter.payload)
    now = time.time()
    if (
        not force
        and maximum == state.get("primary_max")
        and now - float(state.get("scan_at", 0)) < 5
    ):
        await session.commit()
        return
    rows = (
        await session.scalars(
            select(EventRow)
            .where(EventRow.payload[PUBLIC_CURSOR].as_integer().is_(None))
            .order_by(EventRow.cursor)
            .limit(1000)
            .with_for_update(skip_locked=True)
        )
    ).all()
    cursor = int(state.get("last", maximum))
    for row in rows:
        cursor += 1
        row.payload = {**row.payload, PUBLIC_CURSOR: cursor}
    counter.payload = {
        "last": cursor,
        "primary_max": maximum,
        "scan_at": now if len(rows) < 1000 else 0,
    }
    await session.commit()


def event_data(row: EventRow) -> dict[str, Any]:
    return {
        "cursor": int(row.payload.get(PUBLIC_CURSOR, row.cursor)),
        "kind": row.kind,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "run_id": row.run_id,
        "payload": {key: value for key, value in row.payload.items() if key != PUBLIC_CURSOR},
        "created_at": row.created_at.isoformat(),
    }


async def events_after(
    session: AsyncSession,
    owner_id: str,
    cursor: int,
    thread_id: str | None = None,
    limit: int = 200,
) -> list[EventRow]:
    await publish_committed(session)
    public = EventRow.payload[PUBLIC_CURSOR].as_integer()
    query = select(EventRow).where(EventRow.owner_id == owner_id, public > cursor)
    if thread_id:
        query = query.where(EventRow.thread_id == thread_id)
    return list((await session.scalars(query.order_by(public).limit(min(limit, 500)))).all())


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
