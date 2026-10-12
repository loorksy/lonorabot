from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import SecretRow


async def secret_metadata(session: AsyncSession, owner_id: str, scope: str) -> list[dict[str, str]]:
    rows = (
        await session.scalars(
            select(SecretRow).where(SecretRow.owner_id == owner_id, SecretRow.scope == scope)
        )
    ).all()
    return [{"id": r.id, "name": r.name, "updated_at": r.updated_at.isoformat()} for r in rows]
