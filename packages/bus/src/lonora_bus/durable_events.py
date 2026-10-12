import asyncio
from collections.abc import AsyncIterator
from typing import Any

from lonora_db.client import Database
from lonora_db.events import event_data, events_after


async def stream_events(
    db: Database, owner_id: str, cursor: int = 0, thread_id: str | None = None
) -> AsyncIterator[dict[str, Any]]:
    while True:
        async with db.sessions() as session:
            rows = await events_after(session, owner_id, cursor, thread_id)
        if not rows:
            await asyncio.sleep(0.5)
        for row in rows:
            cursor = row.cursor
            yield event_data(row)
