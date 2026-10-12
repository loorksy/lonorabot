from fastapi import APIRouter, Request
from lonora_auth.owner_policy import initialize_owner
from lonora_contracts.auth import OnboardingRequest
from lonora_db.owner import get_owner

from ..middleware.auth import runtime

router = APIRouter(prefix="/onboarding")


@router.get("")
async def status(request: Request) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session:
        return {"owner_initialized": bool(await get_owner(session))}


@router.post("", status_code=201)
async def initialize(request: Request, body: OnboardingRequest) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        await initialize_owner(
            session, body, runtime(request).settings.bootstrap_token.get_secret_value()
        )
    return {"owner_initialized": True}
