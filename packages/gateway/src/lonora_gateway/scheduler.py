from lonora_automation.runner import dispatch_routines
from lonora_db.activation_review import dispatch_activation_reviews
from lonora_db.client import Database
from lonora_db.task_recovery import retry_due_tasks
from lonora_db.task_wait import resume_ready_waits


async def scheduler_tick(db: Database) -> int:
    return (
        await dispatch_routines(db)
        + await retry_due_tasks(db)
        + await dispatch_activation_reviews(db)
        + await resume_ready_waits(db)
    )
