"""Linking the owner's Telegram chat from chat (VISION 11.4, P5).

The bot gives a chat it does not serve a one-time code; the owner types it to an agent in
the app. ``telegram_link`` links that chat only when the owner's own typed message this
run answers contains the code (``owner_message_id``): a code read from a page, a feed, a
peer or any other text links nothing, and the code never needs to reach a card or a screen.
"""

import re
from typing import Any

from lonora_contracts.domain import Contract
from lonora_db.runs import require_lease
from lonora_db.schema import EffectReceiptRow, MessageRow, SteeringRow
from lonora_db.telegram_pairing import ALPHABET, CODE_LENGTH, link_chat
from pydantic import Field
from sqlalchemy import or_, select

from .base import Tool
from .context import ToolContext
from .restrictions import owner_message_id

NAME = "telegram_link"
MAX_MESSAGE = 160


class TelegramLinkInput(Contract):
    code: str = Field(pattern=f"^[{ALPHABET}{ALPHABET.lower()}]{{{CODE_LENGTH}}}$")


async def link(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = TelegramLinkInput.model_validate(args)
    receipt_key = "telegram-link:" + context.resource_id
    async with context.db.sessions() as session, session.begin():
        replayed = await session.get(EffectReceiptRow, receipt_key)
        if replayed is not None:
            return replayed.result  # A crash-replayed call answers as it did.
        run = await require_lease(session, context.lease, lock=True)
        message_id = await owner_message_id(session, run)
        said: list[str] = []
        if message_id is not None:
            added = select(SteeringRow.message_id).where(SteeringRow.run_id == run.id)
            said = list(
                await session.scalars(
                    select(MessageRow.content).where(
                        MessageRow.thread_id == run.thread_id,
                        MessageRow.role == "user",
                        MessageRow.origin == "owner",
                        or_(MessageRow.id == message_id, MessageRow.id.in_(added)),
                    )
                )
            )
        if not any(names_code(str(text), params.code) for text in said):
            return {
                "ok": False,
                "code": "telegram_link_requires_owner_message",
                "linked": False,
                "recovery": "Nothing changed. Only the owner links a chat: ask him to send "
                "the code the bot gave him as a short message of his own.",
            }
        result: dict[str, Any] = (
            {"ok": True, "linked": True, "sends": "the alerts that push, from every agent"}
            if await link_chat(session, context.owner_id, params.code)
            else {
                "ok": False,
                "code": "telegram_code_unknown",
                "linked": False,
                "recovery": "No chat waits with this code: codes last ten minutes, and a bot "
                "that already has a chat offers none (the owner unlinks it to move).",
            }
        )
        session.add(EffectReceiptRow(key=receipt_key, result=result))
    return result


def names_code(text: str, code: str) -> bool:
    """The owner sent the code himself: as a whole word, in a short message. A long pasted
    text (a mail, a page) carrying a code links nothing."""
    return len(text) <= MAX_MESSAGE and bool(
        re.search(rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])", text, re.IGNORECASE)
    )


def tools() -> list[Tool]:
    return [
        Tool(
            NAME,
            "Link the owner's Telegram chat to the linked bot so the alerts that push reach "
            "it. The bot sends the chat a one-time code; use this only with the code the "
            "owner typed to you in his own message.",
            TelegramLinkInput,
            link,
            replay_safe=True,
        )
    ]
