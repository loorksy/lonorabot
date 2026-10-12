import secrets

from lonora_contracts.auth import OnboardingRequest
from lonora_core.user_error import LonoraError
from lonora_db.owner import get_owner
from lonora_db.schema import OwnerRow
from sqlalchemy.ext.asyncio import AsyncSession

from .account_security import hash_password, normalize_email


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
    return row
