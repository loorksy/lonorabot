"""Who a Run speaks for: the owner's typed message, or content others wrote.

``owner_message_id`` stands for the owner's intent only while the Run has read nothing
someone other than the owner wrote; ``mark_external_content`` records that a tool
returned such content into the Run (mandate 6.10, 14.3.5).
"""

from lonora_contracts.domain import utcnow
from lonora_db.owner_words import owner_typed_message
from lonora_db.schema import EffectReceiptRow, MessageRow, RunRow
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

# Runs started by the owner's own message in a conversation or group.
OWNER_TRIGGERS = frozenset({"user", "group"})


def external_content_key(run_id: str) -> str:
    """The receipt that marks a Run as having read content others wrote."""
    return "external-content:" + run_id


async def mark_external_content(session: AsyncSession, run_id: str, tool: str) -> None:
    """Record, once per Run, that a tool returned third-party or other-agent content
    into it (web pages, feeds, MCP servers, peers' memory, stored files, another model).
    Concurrent reads of one segment insert it once."""
    await session.execute(
        insert(EffectReceiptRow)
        .values(key=external_content_key(run_id), result={"tool": tool}, created_at=utcnow())
        .on_conflict_do_nothing(index_elements=[EffectReceiptRow.key])
    )


async def external_content_seen(session: AsyncSession, run: RunRow, after_seq: int) -> bool:
    """Whether this Run has read content someone other than the owner wrote: a tool
    result of that kind (``mark_external_content``) or another agent's message (a peer's
    outcome, a group reply) after the owner's message it answers."""
    if await session.get(EffectReceiptRow, external_content_key(run.id)) is not None:
        return True
    other = await session.scalar(
        select(MessageRow.id)
        .where(
            MessageRow.thread_id == run.thread_id,
            MessageRow.seq > after_seq,
            MessageRow.seq <= run.input_seq,
            MessageRow.agent_id.is_not(None),
            MessageRow.agent_id != run.agent_id,
        )
        .limit(1)
    )
    return other is not None


async def owner_message_id(session: AsyncSession, run: RunRow) -> str | None:
    """The owner's latest message this run answers, or None for non-owner wakes.

    It stands for the owner's intent only while the Run has read nothing someone else
    wrote: once a web page, feed, MCP result, peer's memory or another agent's message
    reached it, injected text could steer the call, so it is None and the sensitive
    tools (supervision, agent creation and control, the owner profile and reach-me,
    model switches, narrowing other agents, lifting a hold) fall back to the owner's
    card or refusal.
    """
    if run.trigger not in OWNER_TRIGGERS:
        return None
    # Only the owner's typed words: a card's send or a follow-up tap never stands for the
    # owner, and a Run a card submission started has none (GENUI_PLAN §8.4).
    found = await owner_typed_message(session, run)
    if found is None:
        return None
    if await external_content_seen(session, run, int(found.seq)):
        return None
    return str(found.id)
