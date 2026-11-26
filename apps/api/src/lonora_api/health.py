import asyncio
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.item_failures import failure_code
from lonora_gateway.health import gateway_health, tell_owner_if_stopped
from sqlalchemy import text

from .middleware.auth import runtime
from .runtime import ApiRuntime

log = logging.getLogger("lonora.api")
router = APIRouter()
# How often this process checks that a Gateway is running.
WATCH_SECONDS = 30.0


async def watch_gateway(rt: ApiRuntime) -> None:
    """Tell the owner when no Gateway runs: this process keeps running when the Gateway
    has stopped, so it raises the item and sends its push (lonora_gateway.health)."""
    from lonora_adapters.channels.expo_push import ExpoPushTransport
    from lonora_security.secrets import SecretCipher

    started = utcnow()
    settings = rt.settings
    cipher = SecretCipher(settings.encryption_key.get_secret_value())
    token = settings.expo_access_token
    transport = ExpoPushTransport(token.get_secret_value() if token else None)
    while True:
        await asyncio.sleep(WATCH_SECONDS)
        try:
            if await tell_owner_if_stopped(rt.db, started, cipher, transport):
                log.error("gateway_not_running")
        except Exception as error:
            log.error("gateway_watch_failed code=%s", failure_code(error))


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    try:
        async with runtime(request).db.sessions() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        raise LonoraError("database_unavailable", 503) from None
    return {"status": "ok"}


@router.get("/ready", response_model=None)
async def readiness(request: Request) -> dict[str, object] | JSONResponse:
    """503 unless a gateway's heartbeat is fresh and none of its critical steps stalled."""
    await health(request)
    gateway = await gateway_health(runtime(request).db)
    from lonora_db.push_devices import push_configured

    async with runtime(request).db.sessions() as session:
        push = await push_configured(session)
    # Push never fails readiness: without a registered phone it reports "not configured".
    body: dict[str, object] = {
        "database": True,
        "gateway": gateway,
        "push": "configured" if push else "not_configured",
    }
    if not gateway["ready"]:
        return JSONResponse(body, status_code=503)
    return body
