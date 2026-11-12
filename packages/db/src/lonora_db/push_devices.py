"""Phones registered for push (VISION 11.4).

A device is registered only through the owner's signed-in session and is bound to it: signing
out deletes it, and a revoked or expired session never receives a push. The token is stored
encrypted; no function here logs it, and nothing here is reachable by a model.
"""

import hashlib
from dataclasses import dataclass

from lonora_contracts.domain import utcnow
from lonora_contracts.push import PushDeviceRegistration
from lonora_security.secrets import SecretCipher
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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
    """One row per device and per token: a re-registration replaces both."""
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
    return [
        PushDevice(row.id, row.device_id, row.platform, cipher.decrypt(row.token_ciphertext))
        for row in rows
    ]
