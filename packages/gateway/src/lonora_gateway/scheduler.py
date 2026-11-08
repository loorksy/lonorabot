import logging

from lonora_automation.runner import dispatch_routines
from lonora_db.activation_review import dispatch_activation_reviews
from lonora_db.client import Database
from lonora_db.item_failures import failure_code
from lonora_db.task_recovery import retry_due_tasks
from lonora_db.task_wait import resume_ready_waits


async def scheduler_tick(db: Database) -> int:
    """One pass of every scheduler step; the gateway runs each as its own supervised step.

    A step that raises is logged and skipped for this pass; it never skips the others.
    """
    changed = 0
    for step in (
        dispatch_routines,
        retry_due_tasks,
        dispatch_activation_reviews,
        resume_ready_waits,
    ):
        try:
            changed += await step(db)
        except Exception as error:
            logging.getLogger("lonora.gateway").error(
                "scheduler_step_failed step=%s code=%s", step.__name__, failure_code(error)
            )
    return changed
