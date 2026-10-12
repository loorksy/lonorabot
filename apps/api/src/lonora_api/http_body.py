from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class BodyLimitMiddleware(BaseHTTPMiddleware):
    maximum = 20 * 1024 * 1024

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > self.maximum):
            return JSONResponse({"code": "request_body_too_large"}, 413)
        if request.method in {"POST", "PUT", "PATCH"}:
            chunks = []
            size = 0
            async for chunk in request.stream():
                size += len(chunk)
                if size > self.maximum:
                    return JSONResponse({"code": "request_body_too_large"}, 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)
