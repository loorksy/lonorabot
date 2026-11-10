from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_automation.delivery import routine_history
from lonora_automation.service import RoutineService
from lonora_contracts.routines import RoutineCreate, RoutineUpdate
from lonora_core.user_error import LonoraError
from lonora_db.routines import owned_routine, routine_data
from lonora_db.schema import RoutineRow
from pydantic import ValidationError
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/routines")


@router.get("")
async def routines(
    request: Request, agent_id: str | None = None, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        query = select(RoutineRow).where(RoutineRow.owner_id == owner.id)
        if agent_id:
            query = query.where(RoutineRow.agent_id == agent_id)
        return [
            routine_data(row)
            for row in (await session.scalars(query.order_by(RoutineRow.next_run_at))).all()
        ]


@router.post("/{agent_id}", status_code=201)
async def create(
    request: Request,
    agent_id: str,
    body: RoutineCreate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    return await RoutineService(runtime(request).db).create(owner.id, agent_id, body)


@router.put("/{routine_id}")
async def update(
    request: Request,
    routine_id: str,
    body: RoutineUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """A partial edit: what the body leaves out keeps its stored value."""
    try:
        return await RoutineService(runtime(request).db).configure(owner.id, routine_id, body)
    except ValidationError as error:
        # The merged routine breaks a schedule rule (run_at_past, one_schedule_required, …).
        message = str(error.errors()[0].get("msg", "invalid_request"))
        raise LonoraError(message.removeprefix("Value error, "), 422) from None


@router.delete("/{routine_id}")
async def delete(
    request: Request, routine_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        await session.delete(await owned_routine(session, owner.id, routine_id))
    return {"deleted": True}


@router.get("/{routine_id}/history")
async def execution_history(
    request: Request, routine_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    return await routine_history(runtime(request).db, routine_id, owner.id)
