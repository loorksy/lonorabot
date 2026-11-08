"""Create a persistent agent from a stored creation spec, with its operating notes.

The database service (``lonora_db.agent_creation``) creates the agent, its ladder level
and its provenance. This adds what every new agent should know from its first run, as
fixed server text in its own operating notes (``OPERATING.md``): its template's role,
and the agents it reports to. Each agent it reports to gets one line saying who reports
to it. The notes are attributed to the owner's request and revertible like any other
memory change. Neither text states authority: the memory guard would refuse it.
"""

from typing import Any

from lonora_core.user_error import LonoraError
from lonora_db.agent_creation import create_root_agent
from lonora_db.memory import commit_memory
from lonora_db.schema import AgentRow
from lonora_db.transactions import owned_agent
from lonora_memory.edits import MemoryEdit, MemoryEditError, MemoryOverflow, apply_edits
from lonora_memory.guard import authority_claim
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
    """Append one operating note; a full or guarded document is left as it is."""

    def transform(current: str, version: int) -> tuple[str, dict[str, Any]]:
        content, _ = apply_edits(
            current, [MemoryEdit(action="add", section="OPERATING.md", content=note)], version
        )
        return content, {}

    try:
        await commit_memory(
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
    return True


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
    notes = [TEMPLATE_NOTES[str(spec["template"])]]
    for target_id in spec.get("report_to", []):
        target = await owned_agent(session, owner_id, target_id)
        notes.append(
            f"Report important findings to {target.name} (agent id {target.id}) with peer_send."
        )
        await _add_note(
            session,
            owner_id,
            target.id,
            f"{row.name} (agent id {row.id}) reports important findings to you.",
            source_message_id,
        )
    for note in notes:
        await _add_note(session, owner_id, row.id, note, source_message_id)
    return row, True
