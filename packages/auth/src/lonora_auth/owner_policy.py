import secrets

from lonora_contracts.auth import OnboardingRequest
from lonora_core.user_error import LonoraError
from lonora_db.owner import get_owner
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import OwnerRow
from sqlalchemy.ext.asyncio import AsyncSession

from .account_security import SITE_HASH, hash_password, normalize_email


async def initialize_owner(
    session: AsyncSession, request: OnboardingRequest, expected_token: str
) -> OwnerRow:
    if not secrets.compare_digest(request.bootstrap_token, expected_token):
        raise LonoraError("invalid_bootstrap_token", 403)
    if await get_owner(session):
        raise LonoraError("owner_already_initialized", 409)
    row = OwnerRow(
        email=normalize_email(request.email), password_hash=hash_password(request.password)
    )
    session.add(row)
    await session.flush()
    await ensure_personal_agent(session, row.id)
    return row


async def import_owner(session: AsyncSession, email: str, password_hash: str) -> OwnerRow:
    """Lonora Cloud: the website account that asked for this installation becomes its owner,
    with the password it signed up with (``SITE_HASH``), so there is no second sign-up."""
    if not SITE_HASH.match(password_hash):
        raise LonoraError("invalid_password", 422)
    if await get_owner(session):
        raise LonoraError("owner_already_initialized", 409)
    row = OwnerRow(email=normalize_email(email), password_hash=password_hash)
    session.add(row)
    await session.flush()
    await ensure_personal_agent(session, row.id)
    return row
