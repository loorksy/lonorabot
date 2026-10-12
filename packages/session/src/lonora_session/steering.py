from typing import Any

from lonora_contracts.domain import MessageCreate
from lonora_db.client import Database
from lonora_db.messages import send_message


async def steer(
    db: Database, owner_id: str, thread_id: str, content: str, nonce: str
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        return await send_message(
            session, owner_id, thread_id, MessageCreate(content=content, client_nonce=nonce)
        )
