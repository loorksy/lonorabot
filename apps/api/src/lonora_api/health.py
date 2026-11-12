from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from lonora_core.user_error import LonoraError
from lonora_gateway.health import gateway_health
from sqlalchemy import text

from .middleware.auth import runtime

router = APIRouter()


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
