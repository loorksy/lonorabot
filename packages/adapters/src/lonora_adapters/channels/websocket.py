from typing import Any

from lonora_db.client import Database
from lonora_db.events import emit


class WebSocketChannelAdapter:
    def __init__(self, db: Database, owner_id: str):
        self.db, self.owner_id = db, owner_id

    async def send(self, destination: str, content: str) -> dict[str, Any]:
        async with self.db.sessions() as session, session.begin():
            emit(
                session,
                self.owner_id,
                "notification.created",
                thread_id=destination,
                payload={"content": content},
            )
        return {"delivered": True}
