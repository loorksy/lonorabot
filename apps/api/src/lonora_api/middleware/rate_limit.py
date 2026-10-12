import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.calls: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if (
            request.url.path not in {"/api/auth/login", "/api/auth/mobile/login", "/api/onboarding"}
            or request.method != "POST"
        ):
            return await call_next(request)
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        queue = self.calls[key]
        while queue and queue[0] < now - 60:
            queue.popleft()
        if len(queue) >= 10:
            return JSONResponse({"code": "rate_limited"}, 429, headers={"Retry-After": "60"})
        queue.append(now)
        if len(self.calls) > 10000:
            self.calls = defaultdict(
                deque, {k: v for k, v in self.calls.items() if v and v[-1] > now - 60}
            )
        return await call_next(request)
