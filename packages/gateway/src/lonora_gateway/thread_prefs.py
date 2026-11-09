"""«إبقاء المحادثات مؤرشفة»: when the owner turned it off, a new message returns an
archived conversation to the list. Applied to every published ``message.created`` event,
whatever wrote the message (``lonora_db.thread_prefs.apply_message_events``)."""

from lonora_db.client import Database
from lonora_db.events import publish_committed
from lonora_db.thread_prefs import apply_message_events


async def thread_prefs_tick(db: Database, owner_id: str) -> int:
    async with db.sessions() as session:
        await publish_committed(session)
    async with db.sessions() as session, session.begin():
        return await apply_message_events(session, owner_id)
