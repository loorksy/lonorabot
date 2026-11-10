from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_core.user_error import LonoraError
from lonora_db.memory import commit_memory, memory_data, read_memory
from lonora_db.memory_revisions import list_revisions, revision_data
from lonora_db.owner_profile import (
    OWNER_PROFILE_CHAR_LIMIT,
    commit_owner_profile,
    enrolled_devices,
    owner_profile_data,
    preference_changes,
    reach_me_policy,
    read_owner_profile,
    revert_revision,
    save_owner_preferences,
)
from lonora_db.schema import MemoryRevisionRow
from lonora_db.transactions import SettingsRepository, owned_agent
from lonora_memory.commit import has_user_section
from lonora_memory.markdown_memory import normalize_memory
from lonora_memory.semantic import index_note
from pydantic import Field

from ..middleware.auth import require_owner, runtime


class MemoryUpdate(Contract):
    content: str = Field(max_length=30000)
    version: int = Field(ge=1)


class OwnerProfileUpdate(Contract):
    # Bounded for transport only: the limit itself is the profile's own rule
    # (``owner_profile_too_large`` with owner text), which lets an over-limit legacy
    # profile be saved shorter.
    content: str = Field(max_length=4 * OWNER_PROFILE_CHAR_LIMIT)
    version: int = Field(ge=1)


class OwnerPreferencesUpdate(Contract):
    """The owner's own preferences, saved as one change: the reach-me policy and reply
    language, and «الاسم» / «طريقة المخاطبة» (WP-H). A field left out stays as it is,
    except reply_language beside a reach_me (the clients that always send both)."""

    reply_language: Literal["ar", "en"] | None = None
    reach_me: IncomingCallPolicy | None = None
    name: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=80)


class RevisionRevert(Contract):
    version: int | None = Field(default=None, ge=1)


router = APIRouter()


@router.get("/agents/{agent_id}/memory")
async def read(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    # The Agent's own view. Owner preferences live in the owner profile; a retired
    # USER.md section of the row was merged there and is kept in the row unread.
    async with runtime(request).db.sessions() as session:
        return memory_data(await read_memory(session, owner.id, agent_id))


@router.put("/agents/{agent_id}/memory")
async def write(
    request: Request,
    agent_id: str,
    body: MemoryUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    if has_user_section(body.content):
        raise LonoraError("memory_user_section_moved", 422)
    async with runtime(request).db.sessions() as session, session.begin():
        return await commit_memory(session, owner.id, agent_id, body.content, body.version)


@router.get("/agents/{agent_id}/memory/revisions")
async def agent_revisions(
    request: Request,
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=50),
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
        rows = await list_revisions(session, owner.id, ("agent_memory",), agent_id, limit)
        return [await revision_data(session, row) for row in rows]


async def profile_payload(request: Request, owner_id: str) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        policy = await reach_me_policy(session, owner_id)
        devices = await enrolled_devices(session, owner_id)
        return {
            **owner_profile_data(await read_owner_profile(session, owner_id)),
            "reach_me": policy.model_dump(mode="json"),
            "devices": [{"id": device.id, "name": device.name} for device in devices],
            "delivery": "in_app_only",
            "shared_with": "every_agent",
        }


@router.get("/owner/profile")
async def read_profile(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    return await profile_payload(request, owner.id)


@router.put("/owner/profile")
async def write_profile(
    request: Request, body: OwnerProfileUpdate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        await commit_owner_profile(
            session, owner.id, normalize_memory(body.content), body.version, author="owner"
        )
    return await profile_payload(request, owner.id)


@router.put("/owner/preferences")
async def write_preferences(
    request: Request, body: OwnerPreferencesUpdate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        fields = body.model_fields_set
        await save_owner_preferences(
            session,
            owner.id,
            policy=body.reach_me,
            reply_language=body.reply_language
            if "reply_language" in fields or body.reach_me is not None
            else "keep",
            name=body.name if "name" in fields else "keep",
            address=body.address if "address" in fields else "keep",
            author="owner",
        )
    return await profile_payload(request, owner.id)


@router.get("/owner/profile/revisions")
async def profile_revisions(
    request: Request,
    limit: int = Query(default=20, ge=1, le=50),
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        rows = await list_revisions(
            session, owner.id, ("owner_profile", "owner_preferences"), None, limit
        )
        return [
            await revision_data(
                session,
                row,
                preference_changes=(
                    preference_changes if row.document == "owner_preferences" else None
                ),
            )
            for row in rows
        ]


@router.post("/memory/revisions/{revision_id}/revert")
async def revert(
    request: Request,
    revision_id: str,
    body: RevisionRevert,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """Undo one change, as a new change attributed to the owner; later changes stay."""
    async with runtime(request).db.sessions() as session, session.begin():
        revision = await session.get(MemoryRevisionRow, revision_id)
        result = await revert_revision(session, owner.id, revision_id, body.version)
        return {"document": revision.document if revision else None, "result": result}


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
