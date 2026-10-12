from lonora_db.client import Database
from lonora_db.usage import UsageRepository

from .models import UsageRecord


async def save_usage(
    db: Database, owner_id: str, agent_id: str, thread_id: str, record: UsageRecord
) -> None:
    async with db.sessions() as session, session.begin():
        await UsageRepository().create(
            session,
            owner_id,
            {
                "run_id": record.run_id,
                "provider": record.provider,
                "model": record.model,
                **record.tokens.model_dump(),
            },
            agent_id=agent_id,
            thread_id=thread_id,
        )
