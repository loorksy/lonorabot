from typing import Any

from lonora_db.client import Database
from lonora_db.messages import history, message_data


async def read_history(
    db: Database, owner_id: str, thread_id: str, limit: int = 100, before: int | None = None
) -> list[dict[str, Any]]:
    async with db.sessions() as session:
        return [
            message_data(row) for row in await history(session, owner_id, thread_id, limit, before)
        ]
