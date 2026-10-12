from contextvars import ContextVar

current_run: ContextVar[str | None] = ContextVar("usage_run", default=None)
