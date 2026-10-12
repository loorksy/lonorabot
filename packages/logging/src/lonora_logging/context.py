from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id: ContextVar[str | None] = ContextVar("run_id", default=None)
