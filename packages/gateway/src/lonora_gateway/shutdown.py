import asyncio
import logging
from collections.abc import Collection
from typing import Any

from lonora_db.client import Database
from lonora_db.runs import release_leases as release

# One shutdown deadline, below the 60 s stop grace the container and systemd give the
# Gateway (docker-compose.prod.yml stop_grace_period, lonora-gateway.service
# TimeoutStopSec). The run drain and the relay drain share it; releasing the leases and
# closing the connections take the time left.
SHUTDOWN_SECONDS = 50
# Runs hand back at their next step boundary. After this the backstop cancels a worker
# still busy (a model stream or a read that does not end), never one inside an effect.
BACKSTOP_SECONDS = 25
# How often the backstop looks again at a worker inside an effect.
EFFECT_POLL_SECONDS = 0.2


async def drain(
    tasks: list[asyncio.Task[None]],
    grace_seconds: float = BACKSTOP_SECONDS,
    deadline_seconds: float = SHUTDOWN_SECONDS,
    effects: Collection[asyncio.Task[Any]] = (),
) -> None:
    """Wait for ``tasks``; past ``grace_seconds``, cancel those still running.

    A task in ``effects`` (a worker inside a call that is not read-only, from
    ``before_effect`` until its result is checkpointed) is never cancelled there: the call
    ends within its own deadline and its Run then hands back at the next boundary. Only
    ``deadline_seconds``, the shutdown deadline, cancels whatever is still left.
    """
    if not tasks:
        return
    clock = asyncio.get_running_loop().time
    deadline = clock() + deadline_seconds
    _, pending = await asyncio.wait(tasks, timeout=grace_seconds)
    cancelled: set[asyncio.Task[None]] = set()
    while pending:
        last = clock() >= deadline
        for task in pending - cancelled:
            if last or task not in effects:
                task.cancel()
                cancelled.add(task)
        if last:
            break
        _, pending = await asyncio.wait(
            pending, timeout=min(EFFECT_POLL_SECONDS, max(0.0, deadline - clock()))
        )
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
