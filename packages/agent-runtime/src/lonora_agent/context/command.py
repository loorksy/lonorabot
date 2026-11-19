"""The / command an owner message is, as the turn that answers it reads it.

The command is written by the server on the owner's message (``lonora_db.messages``). It
tells the Agent what the owner asked for; it grants no tool, permission or authority.
"""

from typing import Any

from lonora_db.schema import MessageRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..skills.loader import load_prompt
from ..skills.registry import legacy_skill_id


def command_of(rich_content: dict[str, Any] | None) -> dict[str, Any] | None:
    parts: list[dict[str, Any]] = (rich_content or {}).get("parts", [])
    return next((part for part in parts if part.get("type") == "command"), None)


def command_block(rich_content: dict[str, Any] | None) -> str:
    """What the command of an owner message asks of the turn, in the runtime's own words."""
    command = command_of(rich_content)
    if command is None:
        return ""
    block = load_prompt("command_" + command["name"])
    # The skill is named by its catalog id, never by its owner-written name.
    return block.replace("{skill_id}", legacy_skill_id(str(command.get("skill_name") or "")))


async def owner_command(
    session: AsyncSession, thread_id: str, input_seq: int
) -> dict[str, Any] | None:
    message = await session.scalar(
        select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq == input_seq)
    )
    return command_of(message.rich_content) if message else None


async def command_context(session: AsyncSession, thread_id: str, input_seq: int) -> str:
    message = await session.scalar(
        select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq == input_seq)
    )
    return command_block(message.rich_content) if message else ""
