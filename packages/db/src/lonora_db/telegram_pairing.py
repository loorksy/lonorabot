"""Pairing the owner's Telegram chat with a linked bot (VISION 11.4, "other channels").

The owner asks for a one-time code (owner session only) and sends ``/start <code>`` to the
bot from the chat that should receive Lonora's alerts. The gateway then stores that chat as
the bot's only destination. The code is kept as a hash, is valid for ten minutes and works
once; a message from any other chat is ignored. Pairing again replaces the chat.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow

PAIRING_LIFETIME = timedelta(minutes=10)
# Unambiguous characters: the owner types the code into Telegram.
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def code_hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


async def telegram_integration(
    session: AsyncSession, owner_id: str, integration_id: str, *, lock: bool = True
) -> IntegrationRow:
    row = await session.get(IntegrationRow, integration_id, with_for_update=lock)
    if row is None or row.owner_id != owner_id or row.payload.get("type") != "telegram":
        raise LonoraError("integration_not_found", 404)
    return row


async def start_pairing(session: AsyncSession, owner_id: str, integration_id: str) -> str:
    row = await telegram_integration(session, owner_id, integration_id)
    code = "".join(secrets.choice(ALPHABET) for _ in range(8))
    row.state = {
        **row.state,
        "pairing": {
            "hash": code_hash(code),
            "expires_at": (utcnow() + PAIRING_LIFETIME).isoformat(),
        },
    }
    return code


def pairing_status(row: IntegrationRow) -> dict[str, Any]:
    return {"paired": bool(row.payload.get("allowed_destinations"))}


def paired_chat(row: IntegrationRow, text: str, chat_id: str, chat_type: str) -> bool:
    """Bind ``chat_id`` when ``text`` is ``/start <code>`` with the current code, sent from a
    private chat; True when it did. The code works once."""
    pairing: dict[str, Any] = row.state.get("pairing") or {}
    parts = text.strip().split()
    if (
        chat_type != "private"
        or len(parts) != 2
        or parts[0] != "/start"
        or not pairing.get("hash")
        or datetime.fromisoformat(str(pairing.get("expires_at"))) <= utcnow()
        or not secrets.compare_digest(code_hash(parts[1]), str(pairing["hash"]))
    ):
        return False
    row.payload = {**row.payload, "allowed_destinations": [chat_id]}
    row.state = {key: value for key, value in row.state.items() if key != "pairing"}
    return True
