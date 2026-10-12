from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import OwnerRow


async def get_owner(session: AsyncSession) -> OwnerRow | None:
    return await session.scalar(select(OwnerRow).where(OwnerRow.singleton == 1))
