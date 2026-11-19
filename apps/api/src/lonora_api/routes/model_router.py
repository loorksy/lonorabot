from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.model_backups import ModelBackups
from lonora_contracts.model_context import ModelContextPolicy
from lonora_contracts.model_routing import Capability, RoutingPolicy
from lonora_core.user_error import LonoraError
from lonora_db.run_retry import retry_unconfigured
from lonora_db.transactions import SettingsRepository
from lonora_providers.routing_policy import read_policy, save_policy

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/settings/models")


async def answer_unconfigured(request: Request, owner: OwnerIdentity) -> None:
    """Once a conversation has a model, the replies that failed only for lack of one are
    queued again, in order, so no message of that time is left without an answer. With
    a key and no routing this is also where the default model is chosen and shown."""
    rt = runtime(request)
    try:
        await rt.services(owner.id).router.usable_route(Capability.CONVERSATION)
    except LonoraError:
        return
    async with rt.db.sessions() as session, session.begin():
        await retry_unconfigured(session, owner.id)


@router.get("")
async def read(request: Request, owner: OwnerIdentity = Depends(require_owner)) -> RoutingPolicy:
    return await read_policy(runtime(request).db)


@router.put("")
async def write(
    request: Request, body: RoutingPolicy, owner: OwnerIdentity = Depends(require_owner)
) -> RoutingPolicy:
    await save_policy(runtime(request).db, body)
    await answer_unconfigured(request, owner)
    return body


@router.put("/backups")
async def backups(
    request: Request, body: ModelBackups, owner: OwnerIdentity = Depends(require_owner)
) -> ModelBackups:
    async with runtime(request).db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "model_backups", body.model_dump(mode="json"))
    await answer_unconfigured(request, owner)
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
