"""Create a persistent agent from a stored creation spec, with its operating notes.

The database service (``lonora_db.agent_creation``) creates the agent, its ladder level
and its provenance. This adds what every new agent should know from its first run, as
fixed server text in its own operating notes (``OPERATING.md``): its template's role,
and the agents it reports to. Each agent it reports to gets one line saying who reports
to it. The notes name agents, never their ids or tools (``list_agents`` holds the link),
are attributed to the owner's request and revertible like any other memory change.
Neither text states authority: the memory guard would refuse it. The exact lines are
kept in the origin record, so deleting the agent takes them out again.
"""

import json
from typing import Any, cast

from lonora_core.user_error import LonoraError
from lonora_db.agent_creation import (
    agent_origin,
    create_root_agent,
    delete_agent,
    origin_key,
    report_targets,
)
from lonora_db.authority_lock import authority_lock
from lonora_db.memory import commit_memory
from lonora_db.schema import AgentRow, SettingRow
from lonora_db.transactions import owned_agent
from lonora_memory.edits import (
    HEADING,
    MemoryEdit,
    MemoryEditError,
    MemoryOverflow,
    apply_edits,
    section_name,
)
from lonora_memory.guard import authority_claim
from lonora_memory.markdown_memory import normalize_memory
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

TEMPLATE_NOTES = {
    "trading": "Trading agent: your focus pair is your default market. You read every market "
    "and trade only within your level and your grant.",
    "general": "General agent: you have no trading pair and do not trade.",
    "research": "Research agent: you have no trading pair and do not trade. Research with web "
    "search, web pages, news feeds and the economic calendar, and report what matters.",
    "supervisor": "Supervisor: you review the work of the agents the owner named and message "
    "them; you never trade for them.",
}


def check_responsibility(text: str) -> None:
    """A responsibility is the agent's standing instruction: it never states authority."""
    if authority_claim(text):
        raise LonoraError("agent_responsibility_authority_claim", 422)


async def _add_note(
    session: AsyncSession, owner_id: str, agent_id: str, note: str, message_id: str | None
) -> bool:
    """Append one operating note; a full or guarded document is left as it is. True only
    when the line was added (not when the same line was already there)."""

    def transform(current: str, version: int) -> tuple[str, dict[str, Any]]:
        content, _ = apply_edits(
            current, [MemoryEdit(action="add", section="OPERATING.md", content=note)], version
        )
        return content, {}

    try:
        result = await commit_memory(
            session,
            owner_id,
            agent_id,
            "",
            None,
            transform=transform,
            source_message_id=message_id,
        )
    except (MemoryEditError, MemoryOverflow):
        return False
    return bool(result.get("changed"))


async def _remove_note(session: AsyncSession, owner_id: str, agent_id: str, note: str) -> None:
    """Take one line this service wrote out of the agent's operating notes; a line the
    owner already changed or removed is left alone."""

    def transform(current: str, version: int) -> tuple[str, dict[str, Any]]:
        del version
        lines = current.split("\n")
        section = None
        for index, line in enumerate(lines):
            heading = HEADING.match(line + "\n")
            if heading:
                section = section_name(heading[1])
            elif section == "OPERATING.md" and line.strip() == note:
                del lines[index]
                return normalize_memory("\n".join(lines)), {}
        return current, {}

    await commit_memory(session, owner_id, agent_id, "", None, transform=transform)


async def create_from_spec(
    session: AsyncSession,
    owner_id: str,
    spec: dict[str, Any],
    *,
    agent_id: str,
    created_via: str,
    created_by_agent_id: str | None,
    source_message_id: str | None,
    run_id: str | None,
    card_id: str | None = None,
) -> tuple[AgentRow, bool]:
    """The agent and whether it is new; a repeated id returns the agent unchanged."""
    check_responsibility(str(spec.get("responsibility") or ""))
    row, created = await create_root_agent(
        session,
        owner_id,
        spec,
        agent_id=agent_id,
        created_via=created_via,
        created_by_agent_id=created_by_agent_id,
        source_message_id=source_message_id,
        run_id=run_id,
        card_id=card_id,
    )
    if not created:
        return row, False
    await _add_note(
        session, owner_id, row.id, TEMPLATE_NOTES[str(spec["template"])], source_message_id
    )
    links: list[dict[str, Any]] = []
    for target_id in spec.get("report_to", []):
        target = await owned_agent(session, owner_id, target_id)
        # Names are quoted as data: a model-chosen name never reads as an instruction in
        # another agent's operating notes.
        own = (
            "Report important findings to the agent named "
            f"{json.dumps(target.name, ensure_ascii=False)}."
        )
        theirs = (
            f"The agent named {json.dumps(row.name, ensure_ascii=False)} "
            "reports important findings to you."
        )
        added_own = await _add_note(session, owner_id, row.id, own, source_message_id)
        added_theirs = await _add_note(session, owner_id, target.id, theirs, source_message_id)
        # Only lines this creation added are recorded, so a delete removes nothing else.
        links.append(
            {
                "agent_id": target.id,
                "own": own if added_own else None,
                "target": theirs if added_theirs else None,
            }
        )
    if links:
        origin = await session.get(SettingRow, origin_key(owner_id, row.id))
        if origin is not None:
            origin.payload = {**origin.payload, "link_notes": links}
    return row, True


def _links(origin: dict[str, Any]) -> list[dict[str, Any]]:
    """The note lines an origin record says its creation wrote, per linked agent."""
    value = origin.get("link_notes")
    if not isinstance(value, list):
        return []
    return [cast(dict[str, Any], item) for item in cast(list[Any], value) if isinstance(item, dict)]


def _link_line(origin: dict[str, Any], agent_id: str, side: str) -> str | None:
    for item in _links(origin):
        if item.get("agent_id") == agent_id:
            line = item.get(side)
            return line if isinstance(line, str) else None
    return None


async def forget_links(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """Before an agent is deleted: the lines its creation wrote into the agents it
    reports to, and the links (and lines) of agents that report to it, go with it.

    Only agents not locked by another change right now are touched, so a delete never
    waits on (or deadlocks with) another delete or edit; a skipped line stays visible
    and revertible in that agent's notes.
    """
    origin = await agent_origin(session, owner_id, agent_id)
    targets = report_targets(origin)
    referrers: list[SettingRow] = [
        row
        for row in await session.scalars(
            select(SettingRow)
            .where(SettingRow.key.startswith("agent-origin:"))
            .order_by(SettingRow.key)
        )
        if row.payload.get("owner_id") == owner_id
        and row.payload.get("agent_id") != agent_id
        and agent_id in report_targets(row.payload)
    ]
    wanted = set(targets) | {str(row.payload["agent_id"]) for row in referrers}
    if not wanted:
        return
    free = set(
        await session.scalars(
            select(AgentRow.id)
            .where(AgentRow.owner_id == owner_id, AgentRow.id.in_(wanted))
            .order_by(AgentRow.id)
            .with_for_update(skip_locked=True)
        )
    )
    for target_id in targets:
        line = _link_line(origin, target_id, "target")
        if target_id in free and line:
            await _remove_note(session, owner_id, target_id, line)
    for row in referrers:
        other = str(row.payload["agent_id"])
        if other not in free:
            continue
        line = _link_line(row.payload, agent_id, "own")
        if line:
            await _remove_note(session, owner_id, other, line)
        row.payload = {
            **row.payload,
            "report_to": [item for item in report_targets(row.payload) if item != agent_id],
            "link_notes": [
                item for item in _links(row.payload) if item.get("agent_id") != agent_id
            ],
        }


async def delete_created_agent(
    session: AsyncSession, owner_id: str, agent_id: str, *, keep_card: str | None = None
) -> None:
    """The owner's delete (``lonora_db.agent_creation.delete_agent``), with the notes and
    links its creation left in other agents removed first."""
    await authority_lock(session, agent_id)
    await owned_agent(session, owner_id, agent_id, lock=True)
    await forget_links(session, owner_id, agent_id)
    await delete_agent(session, owner_id, agent_id, keep_card=keep_card)
