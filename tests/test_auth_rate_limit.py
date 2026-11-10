"""Sign-in, onboarding and enrollment POSTs are limited per client host and per route."""

import httpx
import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route


def app(limit: int | None = None) -> Starlette:
    from lonora_api.middleware.rate_limit import LIMITED, RateLimitMiddleware

    async def ok(request: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    routes = [Route(path, ok, methods=["GET", "POST"]) for path in [*LIMITED, "/api/agents"]]
    application = Starlette(routes=routes)
    if limit is None:
        application.add_middleware(RateLimitMiddleware)
    else:
        application.add_middleware(RateLimitMiddleware, limit=limit)
    return application


def client(application: Starlette) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://t")


def test_the_production_default_is_ten_a_minute_and_the_env_can_raise_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lonora_api.env import Settings

    required = {
        "database_url": "postgresql+asyncpg://x/y",
        "encryption_key": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "bootstrap_token": "b" * 32,
    }
    monkeypatch.delenv("LONORA_AUTH_RATE_LIMIT_PER_MINUTE", raising=False)
    assert Settings(**required, _env_file=None)  # pyright: ignore[reportCallIssue].auth_rate_limit_per_minute == 10
    monkeypatch.setenv("LONORA_AUTH_RATE_LIMIT_PER_MINUTE", "500")
    assert Settings(**required, _env_file=None)  # pyright: ignore[reportCallIssue].auth_rate_limit_per_minute == 500


@pytest.mark.asyncio
async def test_login_brute_force_is_refused_after_the_default_limit():
    async with client(app()) as http:
        codes = [(await http.post("/api/auth/login", json={})).status_code for _ in range(11)]
        assert codes == [200] * 10 + [429]
        refused = await http.post("/api/auth/login", json={})
        assert refused.status_code == 429 and refused.json() == {"code": "rate_limited"}
        assert refused.headers["retry-after"] == "60"
        # Its own bucket: enrolling a device and other routes still answer.
        assert (await http.post("/api/auth/devices/enrollment", json={})).status_code == 200
        assert (await http.post("/api/agents", json={})).status_code == 200
        assert (await http.get("/api/auth/login")).status_code == 200


@pytest.mark.asyncio
async def test_each_route_has_its_own_bucket_and_the_limit_is_configurable():
    async with client(app(limit=3)) as http:
        for path in ("/api/auth/devices/enrollment", "/api/auth/login", "/api/onboarding"):
            codes = [(await http.post(path, json={})).status_code for _ in range(4)]
            assert codes == [200, 200, 200, 429], (path, codes)
