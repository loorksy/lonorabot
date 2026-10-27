import asyncio
from collections.abc import AsyncGenerator
from time import monotonic
from typing import Any

from lonora_db.client import Database
from lonora_db.events import event_data, events_after


async def stream_events(
    db: Database, owner_id: str, cursor: int = 0, thread_id: str | None = None
) -> AsyncGenerator[dict[str, Any], None]:
    # Keep active conversations responsive without multiplying idle queries.
    # Each actual event renews the short delivery window; an idle connection
    # returns to its original polling cadence after the burst ends.
    active_until = monotonic() + 5.0
    while True:
        async with db.sessions() as session:
            rows = await events_after(session, owner_id, cursor, thread_id)
        if not rows:
            await asyncio.sleep(0.1 if monotonic() < active_until else 0.5)
        else:
            active_until = monotonic() + 5.0
        for row in rows:
            event = event_data(row)
            cursor = event["cursor"]
            yield event
