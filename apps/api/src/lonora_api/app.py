import importlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from lonora_core.user_error import LonoraError
from lonora_security.runtime_storage import confined_path

from .env import Settings, get_settings
from .errors import install_errors
from .health import router as health_router
from .http_body import BodyLimitMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIdMiddleware
from .runtime import ApiRuntime

ROUTES = (
    "auth",
    "onboarding",
    "agents",
    "agent_secrets",
    "agent_skills",
    "threads",
    "messages",
    "runs",
    "steering",
    "cancellation",
    "groups",
    "peer_messages",
    "routines",
    "memory",
    "scratchpad",
    "artifacts",
    "boards",
    "tickets",
    "search",
    "mcp",
    "integrations",
    "providers",
    "model_router",
    "usage",
    "voice",
    "market",
    "charts",
    "trading",
    "watches",
    "webhook",
    "events",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    rt = ApiRuntime.create(configuration)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        yield
        await rt.close()

    app = FastAPI(title="Lonora", version="0.2.0", lifespan=lifespan)
    app.state.runtime = rt
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[configuration.allowed_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Request-Id"],
    )
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestIdMiddleware)
    install_errors(app)
    app.include_router(health_router)
    for name in ROUTES:
        module = importlib.import_module("lonora_api.routes." + name)
        app.include_router(module.router, prefix="/api")
    for name in ["events", "market", "voice"]:
        module = importlib.import_module("lonora_api.websocket." + name)
        app.include_router(module.router, prefix="/api")
    build = configuration.web_root.resolve()
    if build.is_dir():

        @app.get("/{path:path}", include_in_schema=False)
        async def web(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise LonoraError("endpoint_not_found", 404)
            candidate = confined_path(build, path) if path else build / "index.html"
            return FileResponse(candidate if candidate.is_file() else build / "index.html")

    return app
