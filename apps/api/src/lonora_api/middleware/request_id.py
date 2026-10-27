import re
from time import perf_counter
from uuid import uuid4

from lonora_logging.context import request_id
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = perf_counter()
        supplied = request.headers.get("x-request-id", "")
        value = supplied if re.fullmatch(r"[a-zA-Z0-9_-]{8,64}", supplied) else str(uuid4())
        token = request_id.set(value)
        request.state.request_id = value
        try:
            response = await call_next(request)
            response.headers["X-Request-Id"] = value
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            if request.method == "POST" and re.fullmatch(
                r"/api/threads/[^/]+/messages", request.url.path
            ):
                timings = {"api": round((perf_counter() - started) * 1000, 2)}
                for name, attribute in (("auth", "auth_ms"), ("message_db", "message_db_ms")):
                    value = getattr(request.state, attribute, None)
                    if isinstance(value, int | float):
                        timings[name] = value
                response.headers["Server-Timing"] = ", ".join(
                    f"{name};dur={duration:.2f}" for name, duration in timings.items()
                )
            return response
        finally:
            request_id.reset(token)
