from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import AgentCreate, AgentUpdate, ThreadCreate
from lonora_db.agents import agent_data, create_agent, list_agents, update_agent
from lonora_db.schema import ThreadRow
from lonora_db.threads import create_thread, thread_data
from lonora_db.transactions import owned_agent
from sqlalchemy import select

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


@router.post("/{agent_id}/conversation")
async def conversation(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        await owned_agent(session, owner.id, agent_id, lock=True)
        row = await session.scalar(
            select(ThreadRow)
            .where(
                ThreadRow.owner_id == owner.id,
                ThreadRow.agent_id == agent_id,
                ThreadRow.group_id.is_(None),
            )
            .order_by(ThreadRow.created_at, ThreadRow.id)
            .limit(1)
        )
        if row is None:
            row = await create_thread(session, owner.id, ThreadCreate(agent_id=agent_id, title=""))
        return thread_data(row)


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
