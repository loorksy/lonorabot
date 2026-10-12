from collections.abc import Generator
from contextlib import contextmanager

from .context import run_id


@contextmanager
def correlate_run(value: str) -> Generator[None]:
    token = run_id.set(value)
    try:
        yield
    finally:
        run_id.reset(token)
