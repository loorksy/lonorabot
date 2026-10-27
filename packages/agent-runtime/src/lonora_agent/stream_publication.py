"""Coalesce provider output without making provider reads wait for storage.

This is a bounded producer/consumer boundary inside one existing model turn.
The consumer still publishes through the canonical leased event writer.
"""

import asyncio
from collections.abc import Awaitable, Callable

MAX_PREVIEW_CHARS = 256000


class StreamPublication:
    def __init__(self, publish: Callable[[str], Awaitable[None]]) -> None:
        self.publish = publish
        self.pending: list[str] = []
        self.size = 0
        self.truncated = False
        self.closed = False
        self.ready = asyncio.Event()
        self.task: asyncio.Task[None] | None = None

    async def offer(self, chunk: str) -> None:
        if self.closed:
            return
        if self.task is not None and self.task.done():
            self.task.result()
        remaining = MAX_PREVIEW_CHARS - self.size
        accepted = chunk[: max(0, remaining)]
        self.truncated |= len(accepted) != len(chunk)
        if not accepted:
            return
        self.size += len(accepted)
        self.pending.append(accepted)
        self.ready.set()
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        text = ""
        while True:
            await self.ready.wait()
            self.ready.clear()
            if self.pending:
                if not self.closed:
                    await asyncio.sleep(0.025)
                text += "".join(self.pending)
                self.pending.clear()
                await self.publish(text)
            if self.closed and not self.pending:
                return

    async def finish(self) -> None:
        self.closed = True
        self.ready.set()
        if self.task is not None:
            await self.task

    async def cancel(self) -> None:
        self.closed = True
        self.pending.clear()
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
