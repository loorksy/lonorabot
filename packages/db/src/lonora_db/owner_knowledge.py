"""Every line of the owner profile with where it came from (8.2, 8.4).

A line is "you_said" when the revision that added it is the owner's own edit or an
Agent's write that answered the owner's typed message, "observed" when Lonora wrote
it without that message, and "earlier" when no kept revision added it or a system
merge did (0039 moved the old USER.md sections in, written under the
owner's-words-only rule). A revert brings a line back with the origin it had before
the reverted change. Agents read observations apart: they are Lonora's inference,
not his word. The owner corrects or deletes one line in «ما أعرفه عنك»; that is
recorded as his word.
"""

import difflib
from typing import Any, Literal

from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .memory_revisions import REVISIONS_KEPT
from .owner_profile import commit_owner_profile, read_owner_profile
from .schema import AgentRow, MemoryRevisionRow

Origin = Literal["you_said", "observed", "earlier"]


def _added(before: str, after: str) -> set[str]:
    return {
        line[2:].strip()
        for line in difflib.ndiff(before.splitlines(), after.splitlines())
        if line.startswith("+ ") and line[2:].strip()
    }


def _origin(revision: MemoryRevisionRow | None) -> Origin:
    if revision is None or revision.author == "system":
        return "earlier"
    said = revision.author == "owner" or (
        revision.author == "agent" and revision.source_message_id is not None
    )
    return "you_said" if said else "observed"


async def profile_lines(session: AsyncSession, owner_id: str) -> dict[str, Any]:
    profile = await read_owner_profile(session, owner_id)
    content = profile.content if profile else ""
    texts = [line.strip() for line in content.splitlines() if line.strip()]
    # Revisions are pruned to REVISIONS_KEPT per document on commit; the limit only
    # states that bound here.
    revisions = (
        await session.scalars(
            select(MemoryRevisionRow)
            .where(
                MemoryRevisionRow.owner_id == owner_id,
                MemoryRevisionRow.document == "owner_profile",
            )
            .order_by(MemoryRevisionRow.created_at.desc(), MemoryRevisionRow.version.desc())
            .limit(REVISIONS_KEPT)
        )
    ).all()
    names = {
        agent.id: agent.name
        for agent in (
            await session.scalars(
                select(AgentRow).where(
                    AgentRow.id.in_(
                        {row.author_agent_id for row in revisions if row.author_agent_id}
                    )
                )
            )
        ).all()
    }
    position = {row.id: index for index, row in enumerate(revisions)}
    added: dict[int, set[str]] = {}

    def adding(text: str, start: int = 0) -> MemoryRevisionRow | None:
        """The newest revision from start on that added text; through a revert, the one
        that added it before the reverted change."""
        for index in range(start, len(revisions)):
            revision = revisions[index]
            if index not in added:
                added[index] = _added(revision.previous_content, revision.content)
            if text not in added[index]:
                continue
            if revision.reverted_revision_id is None:
                return revision
            reverted = position.get(revision.reverted_revision_id)
            return None if reverted is None else adding(text, reverted + 1)
        return None

    lines: list[dict[str, Any]] = []
    for text in dict.fromkeys(texts):
        revision = adding(text)
        lines.append(
            {
                "text": text,
                "origin": _origin(revision),
                "author": revision.author if revision else None,
                "author_agent_name": names.get(revision.author_agent_id or "")
                if revision
                else None,
                "created_at": revision.created_at.isoformat() if revision else None,
            }
        )
    return {"version": profile.version if profile else 1, "lines": lines}


async def correct_line(
    session: AsyncSession, owner_id: str, version: int, text: str, replacement: str | None
) -> dict[str, Any]:
    """Replace (or, with no replacement, delete) every copy of one line, as the owner."""
    target = text.strip()
    new = (replacement or "").strip()

    def correct(current: str, _version: int) -> tuple[str, dict[str, Any]]:
        kept: list[str] = []
        hit = False
        for line in current.splitlines():
            if line.strip() == target:
                hit = True
                if new:
                    kept.append(new)
                continue
            kept.append(line)
        if not hit:
            raise LonoraError("owner_profile_line_not_found", 409)
        result = "\n".join(kept).strip()
        return (result + "\n" if result else ""), {}

    return await commit_owner_profile(
        session, owner_id, "", version, author="owner", transform=correct, change="correction"
    )
