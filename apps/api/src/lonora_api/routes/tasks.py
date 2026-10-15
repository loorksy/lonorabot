from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_db.schema import TicketRow
from lonora_db.tasks import control_task, create_task, get_task, snapshot
from lonora_db.transactions import owned_agent
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/tasks")


@router.get("")
async def list_tasks(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        rows = await session.scalars(
            select(TicketRow)
            .where(TicketRow.owner_id == owner.id, TicketRow.agent_id == agent_id)
            .order_by(TicketRow.updated_at.desc())
            .limit(20)
        )
        return [await snapshot(session, row) for row in rows if row.state.get("task")]


@router.post("", status_code=202)
async def create(
    request: Request,
    body: TaskCreate,
    agent_id: str,
    thread_id: str,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await snapshot(
            session, await create_task(session, owner.id, agent_id, thread_id, body)
        )


@router.get("/{task_id}")
async def read(
    request: Request, task_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return await snapshot(session, await get_task(session, owner.id, task_id))


@router.post("/control")
async def control(
    request: Request, body: TaskControl, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await snapshot(session, await control_task(session, owner.id, body))
