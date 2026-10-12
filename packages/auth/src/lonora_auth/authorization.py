from lonora_db.transactions import owned_agent, owned_thread
from sqlalchemy.ext.asyncio import AsyncSession

from .identity import OwnerIdentity


async def authorize_agent(session: AsyncSession, owner: OwnerIdentity, agent_id: str) -> None:
    await owned_agent(session, owner.id, agent_id)


async def authorize_thread(session: AsyncSession, owner: OwnerIdentity, thread_id: str) -> None:
    await owned_thread(session, owner.id, thread_id)
