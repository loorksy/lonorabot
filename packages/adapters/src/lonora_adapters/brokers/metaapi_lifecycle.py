"""Shared SDK connection ownership; no financial request retry lives here."""

import asyncio
import importlib
import time
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any, cast

from lonora_core.user_error import LonoraError


def is_closed(connection: Any) -> bool:
    return (
        getattr(connection, "_closed", False) is True
        or getattr(getattr(connection, "_meta_api_connection", None), "_closed", False) is True
    )


def retry_time(value: Any) -> float | None:
    """MetaApi's ``recommendedRetryTime`` (an ISO time) as epoch seconds, if readable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def throttled_until(error: BaseException) -> float | None:
    """When MetaApi's TooManyRequests says to retry (epoch seconds), else None."""
    metadata = getattr(error, "metadata", None)
    if type(error).__name__ != "TooManyRequestsException" or not isinstance(metadata, dict):
        return None
    return retry_time(cast(dict[str, Any], metadata).get("recommendedRetryTime"))


def entries(value: Any) -> list[Any]:
    """The values of a dict, the items of a list, else nothing (SDK state is untyped)."""
    if isinstance(value, dict):
        return list(cast(dict[Any, Any], value).values())
    if isinstance(value, list):
        return list(cast(list[Any], value))
    return []


def subscribe_locked_until(websocket: Any) -> float | None:
    """The latest future retry time of the SDK's own subscribe locks: MetaApi refused a
    subscription with TooManyRequests and the SDK waits until then before subscribing
    again. Read only; each Lonora adapter owns its SDK client, so the locks are its own."""
    if websocket is None:
        return None
    locks: list[Any] = [getattr(websocket, "_subscribe_lock", None)]
    for numbers in entries(getattr(websocket, "socket_instances", None)):
        for instances in entries(numbers):
            for instance in entries(instances):
                if isinstance(instance, dict):
                    locks.append(cast(dict[str, Any], instance).get("subscribeLock"))
    times: list[float] = []
    for lock in locks:
        if isinstance(lock, dict):
            moment = retry_time(cast(dict[str, Any], lock).get("recommendedRetryTime"))
            if moment is not None and moment > time.time():
                times.append(moment)
    return max(times, default=None)


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

    def failed(self, failure: LonoraError, until: float | None = None) -> None:
        """``until``: MetaApi's recommended retry time (epoch seconds), never retried
        earlier than that."""
        self.failures += 1
        self.failure = failure
        wait: float = min(30, 2 ** min(self.failures, 5))
        if until is not None:
            wait = max(wait, until - time.time())
        self.retry_at = asyncio.get_running_loop().time() + wait

    def ready(self) -> None:
        self.failure = None
        self.retry_at = 0
        self.failures = 0

    @staticmethod
    def _observe(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()
