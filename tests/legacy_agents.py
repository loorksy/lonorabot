"""A child agent as the removed child-creation path stored it.

Nothing in production creates a child agent any more (step 5b deleted
``child_agent_create``). Rows stored before then keep working until W-AUTH's data
migration (14.3.18.4) makes them ordinary team agents; the checks seed such a row here.
"""

from lonora_db.schema import AgentRow, MemoryRow
from sqlalchemy.ext.asyncio import AsyncSession


async def legacy_child(
    session: AsyncSession, owner_id: str, parent: AgentRow, name: str
) -> AgentRow:
    """A child of an account-bound parent kept its parent's market as a specialist; any
    other child was a delegated research identity with no financial scope."""
    bound = parent.role != "delegated" and parent.trading_account_id is not None
    row = AgentRow(
        owner_id=owner_id,
        parent_id=parent.id,
        name=name,
        role="specialist" if bound else "delegated",
        scope_mode="fixed_market",
        trading_account_id=parent.trading_account_id if bound else None,
        trading_symbol=parent.trading_symbol if bound else None,
    )
    session.add(row)
    await session.flush()
    session.add(MemoryRow(agent_id=row.id))
    return row
