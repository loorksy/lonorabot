from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_backups import ModelBackups
from lonora_contracts.model_routing import RoutingPolicy
from lonora_db.transactions import SettingsRepository
from lonora_providers.routing_policy import read_policy, save_policy

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/settings/models")


@router.get("")
async def read(request: Request, owner: OwnerIdentity = Depends(require_owner)) -> RoutingPolicy:
    return await read_policy(runtime(request).db)


@router.put("")
async def write(
    request: Request, body: RoutingPolicy, owner: OwnerIdentity = Depends(require_owner)
) -> RoutingPolicy:
    await save_policy(runtime(request).db, body)
    return body


@router.put("/backups")
async def backups(
    request: Request, body: ModelBackups, owner: OwnerIdentity = Depends(require_owner)
) -> ModelBackups:
    async with runtime(request).db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "model_backups", body.model_dump(mode="json"))
    return body
