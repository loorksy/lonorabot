import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from lonora_db.client import Database
from lonora_db.events import event_data, events_after


async def stream_events(
    db: Database, owner_id: str, cursor: int = 0, thread_id: str | None = None
) -> AsyncGenerator[dict[str, Any], None]:
    while True:
        async with db.sessions() as session:
            rows = await events_after(session, owner_id, cursor, thread_id)
        if not rows:
            await asyncio.sleep(0.5)
        for row in rows:
            event = event_data(row)
            cursor = event["cursor"]
            yield event
