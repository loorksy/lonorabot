from collections.abc import Iterator
from contextlib import contextmanager

from .context import run_id


@contextmanager
def correlate_run(value: str) -> Iterator[None]:
    token = run_id.set(value)
    try:
        yield
    finally:
        run_id.reset(token)
