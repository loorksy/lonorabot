"""Phones registered for push (VISION 11.4).

A device is registered only through the owner's signed-in session and is bound to it: signing
out deletes it. The token is stored encrypted; no function here logs it, and nothing here is
reachable by a model.
"""

import hashlib
from dataclasses import dataclass

from lonora_contracts.domain import utcnow
from lonora_contracts.push import PushDeviceRegistration
from lonora_core.user_error import LonoraError
from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import aware
from .schema import PushDeviceRow, SessionRow


@dataclass(frozen=True)
class PushDevice:
    id: str
    device_id: str
    platform: str
    token: str


def push_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def register_device(
    session: AsyncSession,
    owner_id: str,
    session_hash: str,
    device_id: str,
    body: PushDeviceRegistration,
    cipher: SecretCipher,
) -> None:
    """One row per device and per token: a re-registration replaces both.

    The session row is locked and read again here, so a sign-out that commits after the
    request was authenticated either waits for this row and deletes it, or is seen and
    refused: no token stays bound to a signed-out session.
    """
    # Two registrations of one owner (one token raced from two installs, or a retry) run one
    # after the other, so the select-then-insert below never trips a unique key.
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "push-devices:" + owner_id},
        )
    signed_in = await session.get(
        SessionRow, session_hash, with_for_update=True, populate_existing=True
    )
    if signed_in is None or signed_in.revoked or aware(signed_in.expires_at) <= utcnow():
        raise LonoraError("unauthorized", 401)
    token = body.token.get_secret_value()
    digest = push_token_hash(token)
    await session.execute(
        delete(PushDeviceRow).where(
            PushDeviceRow.token_hash == digest,
            (PushDeviceRow.owner_id != owner_id) | (PushDeviceRow.device_id != device_id),
        )
    )
    row = await session.scalar(
        select(PushDeviceRow).where(
            PushDeviceRow.owner_id == owner_id, PushDeviceRow.device_id == device_id
        )
    )
    if row is None:
        row = PushDeviceRow(owner_id=owner_id, device_id=device_id)
        session.add(row)
    row.session_hash = session_hash
    row.platform = body.platform
    row.token_hash = digest
    row.token_ciphertext = cipher.encrypt(token)
    row.updated_at = utcnow()


async def remove_device(session: AsyncSession, owner_id: str, device_id: str) -> bool:
    result = await session.execute(
        delete(PushDeviceRow).where(
            PushDeviceRow.owner_id == owner_id, PushDeviceRow.device_id == device_id
        )
    )
    return bool(getattr(result, "rowcount", 0))


async def remove_session_devices(session: AsyncSession, session_hash: str) -> None:
    await session.execute(delete(PushDeviceRow).where(PushDeviceRow.session_hash == session_hash))


async def live_devices(
    session: AsyncSession, owner_id: str, cipher: SecretCipher
) -> list[PushDevice]:
    """The phones a push may go to now: their registering session is neither revoked nor
    expired."""
    rows = await session.scalars(
        select(PushDeviceRow)
        .join(SessionRow, SessionRow.token_hash == PushDeviceRow.session_hash)
        .where(
            PushDeviceRow.owner_id == owner_id,
            SessionRow.revoked.is_(False),
            SessionRow.expires_at > utcnow(),
        )
        .order_by(PushDeviceRow.created_at, PushDeviceRow.id)
    )
    devices: list[PushDevice] = []
    for row in rows:
        try:
            token = cipher.decrypt(row.token_ciphertext)
        except LonoraError:
            # A row the current key cannot read (a rotated key) reaches no one, and never
            # stops the other phones; the app registers it again on its next start.
            continue
        devices.append(PushDevice(row.id, row.device_id, row.platform, token))
    return devices


async def prune_signed_out(session: AsyncSession, owner_id: str) -> None:
    """Delete the phones whose sign-in session was revoked or has expired: a session that
    ended without an explicit sign-out (an expired mobile session, a logout lost offline)
    leaves no token behind."""
    dead = (
        select(SessionRow.token_hash)
        .where(SessionRow.owner_id == owner_id)
        .where(SessionRow.revoked.is_(True) | (SessionRow.expires_at <= utcnow()))
    )
    await session.execute(
        delete(PushDeviceRow).where(
            PushDeviceRow.owner_id == owner_id, PushDeviceRow.session_hash.in_(dead)
        )
    )


async def push_configured(session: AsyncSession) -> bool:
    """Readiness: push is configured once a phone with a live session is registered."""
    row = await session.scalar(
        select(PushDeviceRow.id)
        .join(SessionRow, SessionRow.token_hash == PushDeviceRow.session_hash)
        .where(SessionRow.revoked.is_(False), SessionRow.expires_at > utcnow())
        .limit(1)
    )
    return row is not None
