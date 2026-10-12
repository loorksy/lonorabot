import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from lonora_contracts.events import EventEnvelope


class RuntimeEvents:
    def __init__(self):
        self.subscribers: set[asyncio.Queue[EventEnvelope]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[EventEnvelope]]:
        queue: asyncio.Queue[EventEnvelope] = asyncio.Queue(128)
        self.subscribers.add(queue)
        try:
            yield queue
        finally:
            self.subscribers.discard(queue)

    def publish(self, event: EventEnvelope) -> None:
        for queue in tuple(self.subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)
