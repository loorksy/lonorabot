from typing import Any

from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import ThreadCreate
from lonora_contracts.groups import GroupCreate
from lonora_db.groups import GroupRepository
from lonora_db.threads import create_thread
from lonora_db.transactions import owned_agent, resource_data

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/groups", GroupRepository())


@router.post("/create", status_code=201)
async def create_group(
    request: Request, body: GroupCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        for agent_id in body.member_ids:
            await owned_agent(session, owner.id, agent_id)
        row = await GroupRepository().create(session, owner.id, body.model_dump())
        thread = await create_thread(
            session, owner.id, ThreadCreate(group_id=row.id, title=body.name)
        )
        row.state = {"thread_id": thread.id}
        return {**resource_data(row), "thread_id": thread.id}
