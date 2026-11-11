import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# The bucket each limited POST counts in. Every route that checks a password or the
# bootstrap secret shares one bucket, so a host gets the same number of guesses however
# it splits them; enrolling a device counts on its own.
BUCKETS = {
    "/api/auth/login": "password",
    "/api/auth/mobile/login": "password",
    "/api/onboarding": "password",
    "/api/auth/devices/enrollment": "enrollment",
    "/api/auth/devices/enrollment/verify": "enrollment_verify",
}
LIMITED = frozenset(BUCKETS)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """``limit`` POSTs per minute per client host and bucket: password guesses share one
    bucket, so enrolling a device never spends the sign-in allowance (and the reverse)."""

    def __init__(self, app: ASGIApp, limit: int = 10):
        super().__init__(app)
        self.limit = limit
        self.calls: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path not in LIMITED or request.method != "POST":
            return await call_next(request)
        now = time.monotonic()
        key = (request.client.host if request.client else "unknown", BUCKETS[request.url.path])
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
