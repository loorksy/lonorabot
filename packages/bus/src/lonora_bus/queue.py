import asyncio
from typing import Generic, TypeVar

T = TypeVar("T")


class EventQueue(Generic[T]):
    def __init__(self, capacity: int = 256):
        self.queue: asyncio.Queue[T] = asyncio.Queue(capacity)

    async def put(self, item: T) -> None:
        await self.queue.put(item)

    async def get(self) -> T:
        return await self.queue.get()

    def done(self) -> None:
        self.queue.task_done()
