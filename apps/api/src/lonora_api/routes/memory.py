from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_db.memory import commit_memory, memory_data, read_memory
from lonora_db.transactions import SettingsRepository
from lonora_memory.semantic import index_note
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


class SemanticConfig(Contract):
    enabled: bool = False
    model: str | None = Field(default=None, max_length=200)


class SemanticNote(Contract):
    text: str = Field(min_length=1, max_length=24000)


@router.get("/memory/semantic/config")
async def semantic_config(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return SemanticConfig.model_validate(
            await SettingsRepository().get(session, "semantic_memory")
        ).model_dump()


@router.put("/memory/semantic/config")
async def configure_semantic(
    request: Request, body: SemanticConfig, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    from lonora_core.user_error import LonoraError

    if body.enabled and not body.model:
        raise LonoraError("semantic_model_required", 422)
    async with runtime(request).db.sessions() as session, session.begin():
        await SettingsRepository().put(session, "semantic_memory", body.model_dump())
    return body.model_dump()


@router.post("/agents/{agent_id}/memory/semantic", status_code=201)
async def add_note(
    request: Request,
    agent_id: str,
    body: SemanticNote,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    return await index_note(
        rt.db, rt.services(owner.id).router.credentials, owner.id, agent_id, body.text
    )
