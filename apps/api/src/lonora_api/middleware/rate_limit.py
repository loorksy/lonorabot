import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

LIMITED = frozenset(
    {
        "/api/auth/login",
        "/api/auth/mobile/login",
        "/api/onboarding",
        "/api/auth/devices/enrollment",
        "/api/auth/devices/enrollment/verify",
    }
)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """``limit`` POSTs per minute per client host, counted separately for each route, so
    enrolling a device never spends the sign-in allowance (and the reverse)."""

    def __init__(self, app: ASGIApp, limit: int = 10):
        super().__init__(app)
        self.limit = limit
        self.calls: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path not in LIMITED or request.method != "POST":
            return await call_next(request)
        now = time.monotonic()
        key = (request.client.host if request.client else "unknown", request.url.path)
        queue = self.calls[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= self.limit:
            return JSONResponse({"code": "rate_limited"}, 429, headers={"Retry-After": "60"})
        queue.append(now)
        if len(self.calls) > 10000:
            self.calls = defaultdict(
                deque, {k: v for k, v in self.calls.items() if v and v[-1] > now - 60}
            )
        return await call_next(request)
