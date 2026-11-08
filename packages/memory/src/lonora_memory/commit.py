from typing import Any

from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.memory import MEMORY_CHAR_LIMIT, commit_memory
from lonora_db.owner_profile import OWNER_PROFILE_CHAR_LIMIT, commit_owner_profile
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, MemoryRow, OwnerProfileRow

from .edits import (
    HEADING,
    MemoryEdit,
    MemoryEditError,
    apply_edits,
    authority_refusal,
    new_authority_claim,
)
from .markdown_memory import normalize_memory
from .profile import LEGACY_USER_VIEW, agent_memory_view


class UserSectionMoved(MemoryEditError):
    """Owner preferences live in the shared owner profile, not in an Agent's document."""

    def __init__(self) -> None:
        super().__init__(
            "memory_user_section_moved",
            0,
            recovery="Owner preferences belong in the shared owner profile: write them as "
            "operations with section USER.md. This document keeps MEMORY.md and OPERATING.md.",
        )


def has_user_section(content: str) -> bool:
    return any(match[1] == LEGACY_USER_VIEW for match in HEADING.finditer(content))


def check_agent_document(current: str, content: str) -> None:
    """A whole-document write by an Agent: no owner section, no new authority statement."""
    if has_user_section(content):
        raise UserSectionMoved()
    if claim := new_authority_claim(current, content, profile=False):
        raise authority_refusal(0, claim)


async def atomic_commit(
    db: Database,
    owner_id: str,
    agent_id: str,
    content: str,
    version: int,
    *,
    lease: Lease | None = None,
    effect_key: str | None = None,
    source_message_id: str | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        return await commit_memory(
            session,
            owner_id,
            agent_id,
            normalize_memory(content),
            version,
            effect_key,
            source_run_id=lease.run_id if lease else None,
            validate=check_agent_document if lease else None,
            source_message_id=source_message_id,
        )


def _apply(
    current: str, edits: list[tuple[int, MemoryEdit]], version: int, *, profile: bool
) -> tuple[str, list[dict[str, Any]]]:
    """Apply one document's operations, reporting an error at its index in the call."""
    try:
        return apply_edits(
            current,
            [edit for _, edit in edits],
            version,
            profile=profile,
            limit=OWNER_PROFILE_CHAR_LIMIT if profile else MEMORY_CHAR_LIMIT,
        )
    except MemoryEditError as error:
        error.index = edits[error.index][0]
        raise


async def atomic_edit(
    db: Database,
    owner_id: str,
    agent_id: str,
    edits: list[MemoryEdit],
    version: int | None,
    *,
    lease: Lease | None = None,
    effect_key: str | None = None,
    profile_version: int | None = None,
    source_message_id: str | None = None,
) -> dict[str, Any]:
    """Apply a batch of operations to the locked current revisions, or nothing.

    Operations on section USER.md change the shared owner profile; the others change
    this Agent's own document. Both commit in one transaction under the same receipt
    and lease fence; MemoryEditError and MemoryOverflow roll everything back. Without
    a version an operations batch applies to the current revision: operations are
    content-addressed, so they are checked against whatever is stored.
    """
    own = [(index, edit) for index, edit in enumerate(edits) if edit.section != "USER.md"]
    shared = [(index, edit) for index, edit in enumerate(edits) if edit.section == "USER.md"]
    run_id = lease.run_id if lease else None

    def own_transform(current: str, current_version: int) -> tuple[str, dict[str, Any]]:
        # Retired owner sections in this Agent's row are not part of its view; they
        # leave the row with its next change and stay in that change's revision.
        view = agent_memory_view(current)
        content, applied = _apply(view, own, current_version, profile=False)
        return (current if content == view else content), {"applied": applied}

    def shared_transform(current: str, current_version: int) -> tuple[str, dict[str, Any]]:
        content, applied = _apply(current, shared, current_version, profile=True)
        return content, {"applied": applied}

    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        if effect_key:
            receipt = await session.get(EffectReceiptRow, effect_key)
            if receipt:
                return receipt.result
        results: dict[str, dict[str, Any]] = {}
        if shared:
            if profile_version is None:
                stored = await session.get(OwnerProfileRow, owner_id)
                profile_version = stored.version if stored else 1
            results["owner_profile"] = await commit_owner_profile(
                session,
                owner_id,
                "",
                profile_version,
                author="agent" if lease else "owner",
                author_agent_id=agent_id if lease else None,
                source_message_id=source_message_id,
                source_run_id=run_id,
                transform=shared_transform,
            )
        if own or not shared:
            if version is None:
                stored_memory = await session.get(MemoryRow, agent_id)
                version = stored_memory.version if stored_memory else 1
            results["memory"] = await commit_memory(
                session,
                owner_id,
                agent_id,
                "",
                version,
                source_run_id=run_id,
                transform=own_transform,
                source_message_id=source_message_id,
            )
        if len(results) == 1:
            result = next(iter(results.values()))
        else:
            result = {"changed": any(item.get("changed") for item in results.values()), **results}
        if effect_key:
            session.add(EffectReceiptRow(key=effect_key, result=result))
        return result
