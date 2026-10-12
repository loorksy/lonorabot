from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_db.memory import commit_memory, memory_data, read_memory
from pydantic import Field

from ..middleware.auth import require_owner, runtime


class MemoryUpdate(Contract):
    content: str = Field(max_length=30000)
    version: int = Field(ge=1)


router = APIRouter()


@router.get("/agents/{agent_id}/memory")
async def read(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return memory_data(await read_memory(session, owner.id, agent_id))


@router.put("/agents/{agent_id}/memory")
async def write(
    request: Request,
    agent_id: str,
    body: MemoryUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await commit_memory(session, owner.id, agent_id, body.content, body.version)
