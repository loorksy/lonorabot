import asyncio
import logging

from lonora_db.client import Database
from lonora_db.runs import release_leases as release


async def drain(tasks: list[asyncio.Task[None]], grace_seconds: float = 25) -> None:
    if not tasks:
        return
    _, pending = await asyncio.wait(tasks, timeout=grace_seconds)
    for task in pending:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def release_leases(db: Database, identity: str) -> list[str]:
    """Return this process's leases to the queue after its workers have stopped."""
    try:
        async with db.sessions() as session, session.begin():
            return await release(session, identity)
    except Exception as error:
        # Lease expiry remains the fallback: the next gateway resumes after it.
        logging.getLogger("lonora.gateway").error(
            "lease_release_failed type=%s", type(error).__name__
        )
        return []
