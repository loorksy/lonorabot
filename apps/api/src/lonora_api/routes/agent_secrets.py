from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.agent_secrets import SecretCreate
from lonora_db.secrets import secret_metadata
from lonora_db.transactions import owned_agent

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/agents/{agent_id}/secrets")
async def list_secrets(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, str]]:
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        return await secret_metadata(session, owner.id, "agent:" + agent_id)


@router.post("/agents/{agent_id}/secrets", status_code=201)
async def store_secret(
    request: Request,
    agent_id: str,
    body: SecretCreate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, str]:
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
    secret_id = (
        await runtime(request)
        .services(owner.id)
        .secrets.write(body.name, body.value, "agent:" + agent_id)
    )
    return {"id": secret_id, "name": body.name}


@router.delete("/secrets/{secret_id}")
async def delete_secret(
    request: Request, secret_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    await runtime(request).services(owner.id).secrets.delete(secret_id)
    return {"deleted": True}
