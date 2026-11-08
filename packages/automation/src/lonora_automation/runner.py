from lonora_db.client import Database
from lonora_db.item_failures import ItemGuard
from lonora_db.routines import disable_routine, due_routines, enqueue_one


async def dispatch_routines(db: Database, limit: int = 30) -> int:
    """Each routine fires in its own transaction; one that raises backs off alone."""
    async with db.sessions() as session:
        due = await due_routines(session, limit)
    guard = ItemGuard(db, "routine", quarantine=disable_routine)
    await guard.prepare(identifier for identifier, _ in due)
    enqueued = 0
    for identifier, owner_id in due:

        async def fire(identifier: str = identifier) -> bool:
            async with db.sessions() as session, session.begin():
                return await enqueue_one(session, identifier)

        enqueued += int(bool(await guard.run(identifier, owner_id, fire)))
    return enqueued
