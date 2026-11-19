"""An agent's results from broker-confirmed closes (mandate 5.5.4), from the ledger."""

from typing import Any

from lonora_contracts.execution_quality import PerformanceRead
from lonora_db.client import Database

from .statistics import statistics_block


async def performance_snapshot(
    db: Database, owner_id: str, agent_id: str, params: PerformanceRead
) -> dict[str, Any]:
    async with db.sessions() as session:
        return await statistics_block(
            session, owner_id, agent_id, account_id=params.account_id, symbol=params.symbol
        )
