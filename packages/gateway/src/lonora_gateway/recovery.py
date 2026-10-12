from lonora_contracts.domain import utcnow
from lonora_db.client import Database
from lonora_db.schema import RunRow
from sqlalchemy import select


async def expired_runs(db: Database) -> list[str]:
    async with db.sessions() as session:
        return list(
            (
                await session.scalars(
                    select(RunRow.id).where(
                        RunRow.status.in_(["running", "leased"]),
                        RunRow.lease_expires_at <= utcnow(),
                    )
                )
            ).all()
        )
