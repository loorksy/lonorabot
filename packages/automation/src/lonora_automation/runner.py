from lonora_db.client import Database
from lonora_db.routines import enqueue_due


async def dispatch_routines(db: Database) -> int:
    async with db.sessions() as session, session.begin():
        return await enqueue_due(session)
