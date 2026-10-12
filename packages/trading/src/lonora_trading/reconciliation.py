from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import TradingJournalRow
from lonora_db.trading_journal import persist_result
from sqlalchemy import select


async def reconcile_ambiguous(db: Database, brokers: BrokerManager) -> int:
    async with db.sessions() as session:
        rows = list(
            (
                await session.scalars(
                    select(TradingJournalRow)
                    .where(TradingJournalRow.status.in_(["ambiguous", "submitted"]))
                    .limit(50)
                )
            ).all()
        )
    resolved = 0
    for row in rows:
        try:
            broker = await brokers.get(row.owner_id, row.account_id)
            result = await broker.reconcile(
                row.operation_id, TradeRequest.model_validate(row.request)
            )
        except LonoraError:
            continue
        if result.status not in {"confirmed", "failed"}:
            continue
        async with db.sessions() as session, session.begin():
            await persist_result(
                session, row.operation_id, result.status, result.model_dump(mode="json")
            )
        resolved += 1
    return resolved
