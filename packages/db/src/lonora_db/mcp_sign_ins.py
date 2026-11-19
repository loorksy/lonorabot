"""A sign-in to an MCP server that the owner started from a Secret card (VISION.md 13.1).

It waits until the authorization server sends the owner's browser back to the callback,
which uses it once and only within ``LIFETIME``. What must not be readable in the
database (the PKCE verifier, the server's address, a client secret) is encrypted with
the store's key while it waits, and is gone once the sign-in is used; the state is kept
only as its digest. A sign-in nobody finished in time is deleted when the next one
starts or any comes back.
"""

import hashlib
import json
from datetime import timedelta
from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import McpSignInRow

LIFETIME = timedelta(minutes=10)


def state_digest(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


async def purge_expired(session: AsyncSession) -> None:
    """Sign-ins nobody finished in time can never be used: they go, with their values."""
    await session.execute(
        delete(McpSignInRow).where(
            McpSignInRow.used_at.is_(None), McpSignInRow.expires_at <= utcnow()
        )
    )


async def keep_sign_in(
    session: AsyncSession,
    cipher: SecretCipher,
    owner_id: str,
    card_id: str,
    state: str,
    plan: dict[str, Any],
    hidden: dict[str, str],
) -> None:
    await purge_expired(session)
    session.add(
        McpSignInRow(
            owner_id=owner_id,
            card_id=card_id,
            state_sha256=state_digest(state),
            plan=plan,
            ciphertext=cipher.encrypt(json.dumps(hidden)),
            expires_at=utcnow() + LIFETIME,
        )
    )
    await session.flush()


async def take_sign_in(
    session: AsyncSession, cipher: SecretCipher, state: str
) -> tuple[McpSignInRow, dict[str, str]] | None:
    """The waiting sign-in this state names, now used, and its encrypted values, which the
    row no longer keeps; None when it is unknown, was used already or is late."""
    await purge_expired(session)
    if not state:
        return None
    row = await session.scalar(
        select(McpSignInRow)
        .where(McpSignInRow.state_sha256 == state_digest(state))
        .with_for_update()
    )
    if row is None or row.used_at is not None or row.expires_at <= utcnow():
        return None
    row.used_at = utcnow()
    hidden = cast(dict[str, str], json.loads(cipher.decrypt(row.ciphertext)))
    row.ciphertext = ""
    return row, hidden


async def fail_sign_in(session: AsyncSession, sign_in_id: str, code: str) -> None:
    row = await session.get(McpSignInRow, sign_in_id, with_for_update=True)
    if row is not None:
        row.failure = code


async def sign_in_failed(session: AsyncSession, card_id: str) -> bool:
    """The card's latest sign-in did not finish."""
    latest = await session.scalar(
        select(McpSignInRow.failure)
        .where(McpSignInRow.card_id == card_id)
        .order_by(McpSignInRow.created_at.desc())
        .limit(1)
    )
    return latest is not None
