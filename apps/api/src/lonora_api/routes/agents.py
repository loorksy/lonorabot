from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import AgentCreate, AgentUpdate
from lonora_db.agents import agent_data, create_agent, list_agents, update_agent
from lonora_db.transactions import owned_agent

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("")
async def agents(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [agent_data(row) for row in await list_agents(session, owner.id)]


@router.post("", status_code=201)
async def create(
    request: Request, body: AgentCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return agent_data(await create_agent(session, owner.id, body))


@router.patch("/{agent_id}")
async def configure(
    request: Request,
    agent_id: str,
    body: AgentUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return agent_data(await update_agent(session, owner.id, agent_id, body))


@router.delete("/{agent_id}")
async def delete(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        await session.delete(await owned_agent(session, owner.id, agent_id, lock=True))
    return {"deleted": True}
