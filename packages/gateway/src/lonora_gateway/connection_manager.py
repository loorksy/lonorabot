from collections.abc import Awaitable, Callable


class ConnectionManager:
    def __init__(self):
        self.closers: list[Callable[[], Awaitable[None]]] = []

    def register(self, close: Callable[[], Awaitable[None]]) -> None:
        self.closers.append(close)

    async def close(self) -> None:
        for close in reversed(self.closers):
            await close()
        self.closers.clear()
