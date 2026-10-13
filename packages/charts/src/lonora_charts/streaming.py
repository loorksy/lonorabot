import asyncio
from collections.abc import AsyncIterator
from typing import Any

from lonora_db.client import Database

from .state import inspect_chart


async def chart_stream(db: Database, owner_id: str, chart_id: str) -> AsyncIterator[dict[str, Any]]:
    """Stream committed scenes only. The gateway refreshes independently of consumers."""
    previous: tuple[object, object, object] | None = None
    while True:
        value = await inspect_chart(db, owner_id, chart_id)
        state = value["chart"]["state"]
        revision = (value["chart"]["version"], state.get("scene_version"), value.get("code"))
        if revision != previous:
            previous = revision
            yield value
        await asyncio.sleep(1)
