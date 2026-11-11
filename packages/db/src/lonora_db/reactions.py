"""Quick reactions (Q26, Q28): one of six fixed emojis per reactor and message.

The owner reacts through the owner API, an agent through ``message_react`` in its own
thread. Call and system notices carry no reactions. Every change emits
``message.reaction_updated`` with the message's whole list.
"""

from collections import defaultdict
from typing import Any

from lonora_contracts.reactions import OWNER_REACTOR, REACTION_EMOJIS
from lonora_core.user_error import LonoraError
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import MessageReactionRow, MessageRow
from .thread_prefs import hidden_floor
from .transactions import owned_thread


def reaction_data(row: MessageReactionRow) -> dict[str, Any]:
    return {"reactor": row.reactor, "emoji": row.emoji, "created_at": row.created_at.isoformat()}


async def reactions_by_message(
    session: AsyncSession, message_ids: list[str]
) -> dict[str, list[dict[str, Any]]]:
    """One query for a whole page, oldest reaction first."""
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not message_ids:
        return found
    rows = await session.scalars(
        select(MessageReactionRow)
        .where(MessageReactionRow.message_id.in_(message_ids))
        .order_by(MessageReactionRow.created_at, MessageReactionRow.id)
    )
    for row in rows:
        found[row.message_id].append(reaction_data(row))
    return found


async def reactable_message(session: AsyncSession, thread_id: str, message_id: str) -> MessageRow:
    message = await session.get(MessageRow, message_id)
    # Call and system notices, and tool rows, take no reaction.
    if (
        message is None
        or message.thread_id != thread_id
        or message.role
        not in {
            "user",
            "assistant",
        }
    ):
        raise LonoraError("message_not_found", 404)
    return message


async def _write(
    session: AsyncSession,
    owner_id: str,
    message: MessageRow,
    reactor: str,
    emoji: str | None,
) -> dict[str, Any]:
    if emoji is not None and emoji + "️" in REACTION_EMOJIS:
        # ❤ without its emoji presentation selector is the same reaction as ❤️.
        emoji += "️"
    if emoji is not None and emoji not in REACTION_EMOJIS:
        raise LonoraError("reaction_not_allowed", 422)
    await session.execute(
        delete(MessageReactionRow).where(
            MessageReactionRow.message_id == message.id, MessageReactionRow.reactor == reactor
        )
    )
    if emoji is not None:
        session.add(
            MessageReactionRow(
                message_id=message.id, thread_id=message.thread_id, reactor=reactor, emoji=emoji
            )
        )
    await session.flush()
    reactions = (await reactions_by_message(session, [message.id])).get(message.id, [])
    emit(
        session,
        owner_id,
        "message.reaction_updated",
        thread_id=message.thread_id,
        payload={"thread_id": message.thread_id, "message_id": message.id, "reactions": reactions},
    )
    return {"message_id": message.id, "reactions": reactions}


async def owner_reaction(
    session: AsyncSession, owner_id: str, thread_id: str, message_id: str, emoji: str | None
) -> dict[str, Any]:
    """Set (``emoji``) or remove (``None``) the owner's one reaction. A message hidden by
    the owner's «مسح» is ``message_not_found``."""
    # The thread lock serializes the owner's replace with an agent's reaction.
    await owned_thread(session, owner_id, thread_id, lock=True)
    message = await reactable_message(session, thread_id, message_id)
    if message.seq <= await hidden_floor(session, owner_id, thread_id):
        raise LonoraError("message_not_found", 404)
    return await _write(session, owner_id, message, OWNER_REACTOR, emoji)


async def agent_reaction(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    thread_id: str,
    message_id: str,
    emoji: str | None,
) -> dict[str, Any]:
    """The agent's one reaction in its own Run's thread; ``None`` removes it."""
    await owned_thread(session, owner_id, thread_id, lock=True)
    message = await reactable_message(session, thread_id, message_id)
    return await _write(session, owner_id, message, agent_id, emoji)
