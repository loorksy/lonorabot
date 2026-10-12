from lonora_automation.runner import dispatch_routines
from lonora_db.client import Database


async def routine_tick(db: Database) -> int:
    return await dispatch_routines(db)
