from lonora_contracts.domain import MessageCreate
from lonora_db.client import Database
from lonora_db.messages import send_message

from .contracts import IncomingMessage
from .validation import require_destination


async def receive_message(
    db: Database, owner_id: str, message: IncomingMessage, allowed: set[str]
) -> dict[str, object]:
    require_destination(message.destination, allowed)
    async with db.sessions() as session, session.begin():
        return await send_message(
            session,
            owner_id,
            message.thread_id,
            MessageCreate(content=message.content, client_nonce="channel:" + message.external_id),
        )
