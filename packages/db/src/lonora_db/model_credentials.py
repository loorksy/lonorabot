from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import SecretRow


async def credential_id(session: AsyncSession, provider: str) -> str | None:
    row = await session.scalar(
        select(SecretRow).where(SecretRow.scope == "provider", SecretRow.name == provider)
    )
    return row.id if row else None
