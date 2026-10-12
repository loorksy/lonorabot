import hashlib
import secrets
from datetime import timedelta

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.runs import aware
from lonora_db.schema import OwnerRow, SessionRow
from sqlalchemy.ext.asyncio import AsyncSession

from .identity import OwnerIdentity


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


async def issue_session(session: AsyncSession, owner: OwnerRow, duration: int) -> tuple[str, str]:
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session.add(
        SessionRow(
            token_hash=token_hash(token),
            owner_id=owner.id,
            csrf_hash=token_hash(csrf),
            expires_at=utcnow() + timedelta(seconds=duration),
        )
    )
    return token, csrf


async def read_session(session: AsyncSession, token: str | None) -> OwnerIdentity:
    if not token:
        raise LonoraError("unauthorized", 401)
    row = await session.get(SessionRow, token_hash(token))
    if row is None or row.revoked or aware(row.expires_at) <= utcnow():
        raise LonoraError("unauthorized", 401)
    owner = await session.get(OwnerRow, row.owner_id)
    if owner is None:
        raise LonoraError("unauthorized", 401)
    return OwnerIdentity(owner.id, owner.email, row.token_hash)


async def revoke(session: AsyncSession, identity: OwnerIdentity) -> None:
    row = await session.get(SessionRow, identity.token_hash)
    if row:
        row.revoked = True


async def check_csrf(session: AsyncSession, identity: OwnerIdentity, supplied: str | None) -> None:
    row = await session.get(SessionRow, identity.token_hash)
    if (
        row is None
        or not supplied
        or not secrets.compare_digest(row.csrf_hash, token_hash(supplied))
    ):
        raise LonoraError("csrf_required", 403)
