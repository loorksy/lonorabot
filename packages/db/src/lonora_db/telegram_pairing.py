"""Pairing the owner's Telegram chat with a linked bot, from chat (VISION 11.4, P5).

A private chat that writes to a bot with no paired chat gets a one-time code from the bot.
The owner types that code to Lonora in the app, and the agent links the chat with
``telegram_link``, which works only when the owner's own typed message this run answers
contains the code (``owner_message_id``). So the code proves the Telegram chat and the
owner's typed message proves the owner: a code that reached the model, a page or another
chat links nothing by itself. A code is kept as a hash, is valid for ten minutes and works
once; at most three chats wait at a time. Pairing again replaces the chat.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import PUBLIC_CURSOR
from .schema import EventRow, IntegrationRow

PAIRING_LIFETIME = timedelta(minutes=10)
MAX_WAITING = 3
# Unambiguous characters: the owner types the code into the app.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
# What the bot answers a chat it does not serve yet: fixed text, the code, nothing else.
OFFER_TEXT = {
    "ar": "لربط هذه المحادثة بـ Lonora، أرسل هذا الرمز إلى Lonora في التطبيق "
    "خلال عشر دقائق: {code}",
    "en": "To link this chat with Lonora, send this code to Lonora in the app within ten "
    "minutes: {code}",
}


def code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def waiting(row: IntegrationRow, now: datetime) -> dict[str, dict[str, Any]]:
    pending: dict[str, dict[str, Any]] = row.state.get("pending_chats") or {}
    return {
        key: value
        for key, value in pending.items()
        if datetime.fromisoformat(str(value.get("expires_at"))) > now
    }


def offer_code(row: IntegrationRow, chat_id: str) -> str | None:
    """A fresh code for ``chat_id``, replacing its earlier one; None while three other chats
    already wait (a stranger cannot fill the bot's state)."""
    now = utcnow()
    pending = {
        key: value for key, value in waiting(row, now).items() if value["chat_id"] != chat_id
    }
    if len(pending) >= MAX_WAITING:
        return None
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LENGTH))
    pending[code_hash(code)] = {
        "chat_id": chat_id,
        "expires_at": (now + PAIRING_LIFETIME).isoformat(),
    }
    row.state = {**row.state, "pending_chats": pending}
    return code


async def link_chat(session: AsyncSession, owner_id: str, code: str) -> bool:
    """Make the chat that received ``code`` the only destination of its bot; True when a
    waiting chat had that code. Delivery starts at the end of the event stream."""
    digest = code_hash(code)
    now = utcnow()
    rows = await session.scalars(
        select(IntegrationRow).where(IntegrationRow.owner_id == owner_id).with_for_update()
    )
    for row in rows:
        if row.payload.get("type") != "telegram":
            continue
        found = waiting(row, now).get(digest)
        if found is None:
            continue
        latest = await session.scalar(
            select(func.max(EventRow.payload[PUBLIC_CURSOR].as_integer())).where(
                EventRow.owner_id == owner_id
            )
        )
        row.payload = {**row.payload, "allowed_destinations": [str(found["chat_id"])]}
        row.state = {
            **{key: value for key, value in row.state.items() if key != "pending_chats"},
            "event_cursor": int(latest or 0),
        }
        return True
    return False
