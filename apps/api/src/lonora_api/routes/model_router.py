from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_backups import ModelBackups
from lonora_contracts.model_context import ModelContextPolicy
from lonora_contracts.model_routing import AllowedModels, RoutingPolicy
from lonora_db.agent_models import added_models, routed_models, save_added_models
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


@router.get("/context")
async def read_context(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> ModelContextPolicy:
    async with runtime(request).db.sessions() as session:
        return ModelContextPolicy.model_validate(
            await SettingsRepository().get(session, "model_context")
        )


@router.put("/context")
async def write_context(
    request: Request, body: ModelContextPolicy, owner: OwnerIdentity = Depends(require_owner)
) -> ModelContextPolicy:
    async with runtime(request).db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "model_context", body.model_dump(mode="json"))
    return body


async def allowed_view(request: Request) -> dict[str, object]:
    async with runtime(request).db.sessions() as session:
        routed = await routed_models(session)
        added = (await added_models(session)).added
    return {
        # The global text routes and backups: always allowed, changed above.
        "routed": [item.model_dump(mode="json") for item in routed],
        # The owner's additions: agents may choose these on their own too.
        "added": [item.model_dump(mode="json") for item in added],
    }


@router.get("/allowed")
async def read_allowed(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, object]:
    return await allowed_view(request)


@router.put("/allowed")
async def write_allowed(
    request: Request, body: AllowedModels, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, object]:
    async with runtime(request).db.sessions() as session, session.begin():
        await save_added_models(session, body)
    return await allowed_view(request)
