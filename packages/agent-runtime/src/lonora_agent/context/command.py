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


async def owner_command(
    session: AsyncSession, thread_id: str, input_seq: int
) -> dict[str, Any] | None:
    message = await session.scalar(
        select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq == input_seq)
    )
    content: dict[str, Any] = (message.rich_content if message else None) or {}
    parts: list[dict[str, Any]] = content.get("parts", [])
    return next((part for part in parts if part.get("type") == "command"), None)


async def command_context(session: AsyncSession, thread_id: str, input_seq: int) -> str:
    command = await owner_command(session, thread_id, input_seq)
    if command is None:
        return ""
    block = load_prompt("command_" + command["name"])
    # The skill is named by its catalog id, never by its owner-written name.
    return block.replace("{skill_id}", legacy_skill_id(str(command.get("skill_name") or "")))
