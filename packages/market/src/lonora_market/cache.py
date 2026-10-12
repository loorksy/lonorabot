import time
from typing import Generic, TypeVar

T = TypeVar("T")


class MarketCache(Generic[T]):
    def __init__(self, maximum: int = 256):
        self.entries: dict[str, tuple[float, T]] = {}
        self.maximum = maximum

    def get(self, key: str) -> T | None:
        item = self.entries.get(key)
        if item is None or item[0] < time.monotonic():
            self.entries.pop(key, None)
            return None
        return item[1]

    def put(self, key: str, value: T, ttl: float = 3) -> None:
        if len(self.entries) >= self.maximum:
            self.entries.pop(next(iter(self.entries)))
        self.entries[key] = (time.monotonic() + ttl, value)
