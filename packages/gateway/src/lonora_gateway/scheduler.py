from lonora_automation.runner import dispatch_routines
from lonora_db.client import Database
from lonora_db.task_recovery import retry_due_tasks


async def scheduler_tick(db: Database) -> int:
    return await dispatch_routines(db) + await retry_due_tasks(db)
