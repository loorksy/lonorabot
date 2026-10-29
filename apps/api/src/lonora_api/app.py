import importlib
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from lonora_core.user_error import LonoraError
from lonora_security.runtime_storage import confined_path

from .chart_renderer import install_chart_renderer
from .env import Settings, get_settings
from .errors import install_errors
from .health import router as health_router
from .http_body import BodyLimitMiddleware
from .middleware.rate_limit import RateLimitMiddleware
from .middleware.request_id import RequestIdMiddleware
from .runtime import ApiRuntime

ROUTES = (
    "mobile_updates",
    "auth",
    "device_authority",
    "account_authority",
    "agent_permissions",
    "onboarding",
    "agents",
    "agent_state",
    "execution_mode",
    "attention",
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
    "incoming_calls",
    "market",
    "charts",
    "trading",
    "trading_goals",
    "trading_decisions",
    "opportunities",
    "execution_policy",
    "tasks",
    "collaboration",
    "watches",
    "webhook",
    "events",
)


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings or get_settings()
    rt = ApiRuntime.create(configuration)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        from lonora_db.owner import get_owner
        from lonora_db.personal_agent import ensure_personal_agent

        async with rt.db.sessions() as session, session.begin():
            owner = await get_owner(session)
            if owner:
                await ensure_personal_agent(session, owner.id)
        yield
        await rt.close()

    app = FastAPI(title="Lonora", version="0.2.0", lifespan=lifespan)

    @app.get("/.well-known/assetlinks.json", include_in_schema=False)
    async def android_app_links():
        from .device_metadata import asset_links

        return asset_links(configuration)

    @app.get("/.well-known/apple-app-site-association", include_in_schema=False)
    async def apple_app_links():
        return {"webcredentials": {"apps": configuration.passkey_ios_app_ids}}

    app.state.runtime = rt
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[configuration.allowed_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Authorization", "X-Request-Id"],
        expose_headers=["X-Request-Id", "Server-Timing"],
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

    @app.api_route("/download/lonora.apk", methods=["GET", "HEAD"], include_in_schema=False)
    async def android_download() -> FileResponse:
        apk = configuration.android_apk_path
        try:
            if not apk.is_file():
                raise LonoraError("android_release_unavailable", 404)
            with apk.open("rb") as stream:
                if stream.read(4) != b"PK\x03\x04":
                    raise LonoraError("android_release_invalid", 503)
        except OSError:
            raise LonoraError("android_release_unavailable", 503) from None
        return FileResponse(
            apk,
            media_type="application/vnd.android.package-archive",
            filename="lonora.apk",
            headers={"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
        )

    install_chart_renderer(app, configuration.chart_renderer_root or configuration.web_root)
    build = configuration.web_root.resolve()
    if build.is_dir():

        @app.get("/{path:path}", include_in_schema=False)
        async def web(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise LonoraError("endpoint_not_found", 404)
            candidate = confined_path(build, path) if path else build / "index.html"
            target = candidate if candidate.is_file() else build / "index.html"
            # The shell selects hashed application assets. Heuristic caching of
            # HTML can keep the old UI after deployment even though those assets
            # and the server are current. Hashed chart/application bundles retain
            # their separate asset-cache policy in install_chart_renderer.
            return FileResponse(
                target,
                headers={
                    "Cache-Control": "no-store" if target.suffix == ".html" else "no-cache",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    return app
