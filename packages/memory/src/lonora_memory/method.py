"""Versions of an Agent's method: the ``# OPERATING.md`` section of its memory.

Every commit of an Agent's memory keeps an attributed revision (``ln_memory_revisions``).
A method version is a revision whose OPERATING.md text differs from the text before it;
its number is the memory version that commit created. Restoring version N saves a new
revision whose OPERATING.md text equals version N's and leaves MEMORY.md as it is now.
"""

from typing import Any

from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.memory import VIEW_HEADING, commit_memory, method_text
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, MemoryRevisionRow, MemoryRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .edits import new_authority_claim
from .profile import OPERATING_VIEW

EXCERPT_CHARS = 240


def with_operating(view: str, text: str) -> str:
    """``view`` with its OPERATING.md text replaced by ``text``; every other part kept
    byte for byte (split method sections become one, at the first one's place)."""
    body = text.strip()
    source = view if not view or view.endswith("\n") else view + "\n"
    matches = list(VIEW_HEADING.finditer(source))
    parts = [source[: matches[0].start()] if matches else source]
    placed = False
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(source)
        if match[1] != OPERATING_VIEW:
            parts.append(source[match.start() : end])
        elif not placed:
            placed = True
            if body:
                tail = "\n\n" if position + 1 < len(matches) else "\n"
                parts.append(f"# {OPERATING_VIEW}\n{body}{tail}")
    if not placed and body:
        head = "".join(parts).rstrip("\n")
        parts = [head + ("\n\n" if head.strip() else ""), f"# {OPERATING_VIEW}\n{body}\n"]
    result = "".join(parts).rstrip("\n")
    return result + "\n" if result.strip() else ""


async def method_revisions(
    session: AsyncSession, owner_id: str, agent_id: str
) -> list[MemoryRevisionRow]:
    """Every kept revision that changed the method, newest first."""
    rows = await session.scalars(
        select(MemoryRevisionRow)
        .where(
            MemoryRevisionRow.owner_id == owner_id,
            MemoryRevisionRow.document == "agent_memory",
            MemoryRevisionRow.agent_id == agent_id,
        )
        .order_by(MemoryRevisionRow.version.desc(), MemoryRevisionRow.created_at.desc())
    )
    return [row for row in rows if method_text(row.content) != method_text(row.previous_content)]


def version_data(row: MemoryRevisionRow, *, current: bool, text: bool) -> dict[str, Any]:
    method = method_text(row.content)
    data: dict[str, Any] = {
        "version": row.version,
        "created_at": row.created_at.isoformat(),
        "author": row.author,
        "from_owner_message": row.source_message_id is not None,
        "change": row.change,
        "chars": len(method),
        "current": current,
    }
    if text:
        data["text"] = method
    else:
        data["excerpt"] = method[:EXCERPT_CHARS]
    return data


async def method_history(
    session: AsyncSession, owner_id: str, agent_id: str, *, version: int | None = None
) -> dict[str, Any]:
    """The method's versions, newest first; with ``version``, that version's full text."""
    rows = await method_revisions(session, owner_id, agent_id)
    current = rows[0].version if rows else None
    memory = await session.get(MemoryRow, agent_id)
    memory_version = memory.version if memory else None
    if version is not None:
        row = next((item for item in rows if item.version == version), None)
        if row is None:
            raise LonoraError("method_version_not_found", 404)
        return {
            "version": version_data(row, current=row.version == current, text=True),
            "memory_version": memory_version,
        }
    return {
        "versions": [
            version_data(row, current=row.version == current, text=False) for row in rows[:50]
        ],
        "total": len(rows),
        "memory_version": memory_version,
    }


async def restore_method(
    db: Database,
    owner_id: str,
    agent_id: str,
    version: int,
    expected_version: int,
    *,
    lease: Lease,
    effect_key: str,
    source_message_id: str | None = None,
    author_agent_id: str | None = None,
) -> dict[str, Any]:
    """Save version ``version`` of the method as a new revision; MEMORY.md is untouched."""
    async with db.sessions() as session, session.begin():
        await require_lease(session, lease, lock=True)
        if receipt := await session.get(EffectReceiptRow, effect_key):
            return receipt.result
        rows = await method_revisions(session, owner_id, agent_id)
        target = next((row for row in rows if row.version == version), None)
        if target is None:
            raise LonoraError("method_version_not_found", 404)
        text = method_text(target.content)

        def transform(current: str, _: int) -> tuple[str, dict[str, Any]]:
            if method_text(current) == text:
                # Already this version: save nothing rather than a version that changes
                # only the layout.
                return current, {"restored_version": version}
            restored = with_operating(current, text)
            if new_authority_claim(current, restored, profile=False):
                raise LonoraError("memory_authority_claim_refused", 409)
            return restored, {"restored_version": version}

        return await commit_memory(
            session,
            owner_id,
            agent_id,
            "",
            expected_version,
            effect_key,
            source_run_id=lease.run_id,
            transform=transform,
            source_message_id=source_message_id,
            change="restore",
            author_agent_id=author_agent_id,
        )
