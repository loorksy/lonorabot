import asyncio
import logging
from collections.abc import Awaitable, Callable


async def supervise(name: str, loop: Callable[[], Awaitable[None]], stop: asyncio.Event) -> None:
    failures = 0
    while not stop.is_set():
        try:
            await loop()
            failures = 0
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failures += 1
            logging.getLogger("lonora.gateway").error(
                "loop_failed name=%s type=%s", name, type(error).__name__
            )
        try:
            await asyncio.wait_for(stop.wait(), min(30, 2 ** min(failures, 5)))
        except TimeoutError:
            continue
