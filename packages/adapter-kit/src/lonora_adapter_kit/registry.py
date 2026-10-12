from collections.abc import Callable
from typing import Generic, TypeVar

from lonora_core.user_error import LonoraError

T = TypeVar("T")


class AdapterRegistry(Generic[T]):
    def __init__(self) -> None:
        self._factories: dict[str, Callable[..., T]] = {}

    def register(self, name: str, factory: Callable[..., T]) -> None:
        if name in self._factories:
            raise LonoraError("adapter_already_registered", 409)
        self._factories[name] = factory

    def create(self, name: str, **kwargs: object) -> T:
        factory = self._factories.get(name)
        if factory is None:
            raise LonoraError("adapter_not_supported", 404)
        return factory(**kwargs)

    def names(self) -> list[str]:
        return sorted(self._factories)
