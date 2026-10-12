from fastapi import APIRouter, Request
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


@router.get("/ready")
async def readiness(request: Request) -> dict[str, object]:
    await health(request)
    return {"database": True, "gateway": await gateway_health(runtime(request).db)}
