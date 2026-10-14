"""Shared SDK connection ownership; no financial request retry lives here."""

import asyncio
import importlib
from collections.abc import Callable, Coroutine
from typing import Any

from lonora_core.user_error import LonoraError


def is_closed(connection: Any) -> bool:
    return (
        getattr(connection, "_closed", False) is True
        or getattr(getattr(connection, "_meta_api_connection", None), "_closed", False) is True
    )


def closed_error(error: Exception) -> bool:
    return "connection has been closed" in str(error).casefold()


def synchronized(connection: Any, kind: str) -> bool:
    shared = getattr(connection, "_meta_api_connection", None)
    if shared is None:
        return False
    if kind == "rpc":
        return shared.is_synchronized() is True
    return shared.synchronized is True


class NoFileHistoryDatabase:
    """SDK history cache is disposable; durable application evidence lives in PostgreSQL."""

    async def load_history(self, account_id: str, application: str) -> dict[str, list[Any]]:
        return {"deals": [], "historyOrders": []}

    async def clear(self, account_id: str, application: str) -> None:
        return None

    async def flush(self, *args: Any) -> None:
        return None


def history_storage() -> Any:
    # get_streaming_connection accepts a HistoryStorage implementation. MemoryHistoryStorage
    # otherwise silently uses FilesystemHistoryDatabase in .metaapi relative to cwd.
    storage: Any = importlib.import_module(
        "metaapi_cloud_sdk.metaapi.memory_history_storage"
    ).MemoryHistoryStorage()
    storage._history_database = NoFileHistoryDatabase()
    return storage


class ConnectionSlot:
    def __init__(self, kind: str):
        self.kind = kind
        self.lock = asyncio.Lock()
        self.task: asyncio.Task[Any] | None = None
        self.failure: LonoraError | None = None
        self.retry_at = 0.0
        self.failures = 0

    async def get(self, create: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        async with self.lock:
            now = asyncio.get_running_loop().time()
            if self.failure is not None and now < self.retry_at:
                raise self.failure
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(create())
                # Initialization survives individual consumer cancellations; retrieve
                # failures even if every original consumer was cancelled meanwhile.
                self.task.add_done_callback(self._observe)
            task = self.task
        # A cancelled stream consumer must not cancel shared account initialization.
        return await asyncio.shield(task)

    def failed(self, failure: LonoraError) -> None:
        self.failures += 1
        self.failure = failure
        self.retry_at = asyncio.get_running_loop().time() + min(30, 2 ** min(self.failures, 5))

    def ready(self) -> None:
        self.failure = None
        self.retry_at = 0
        self.failures = 0

    @staticmethod
    def _observe(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()
