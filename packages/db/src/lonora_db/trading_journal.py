from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import TradingJournalRow


async def reserve_operation(
    session: AsyncSession,
    owner_id: str,
    operation_id: str,
    account_id: str,
    request_hash: str,
    request: dict[str, Any],
) -> tuple[TradingJournalRow, bool]:
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row:
        if row.owner_id != owner_id or row.request_hash != request_hash:
            raise LonoraError("operation_id_conflict", 409)
        return row, False
    row = TradingJournalRow(
        operation_id=operation_id,
        owner_id=owner_id,
        account_id=account_id,
        request_hash=request_hash,
        request=request,
    )
    session.add(row)
    await session.flush()
    return row, True


async def journal_entries(
    session: AsyncSession, owner_id: str, account_id: str | None = None
) -> list[TradingJournalRow]:
    query = select(TradingJournalRow).where(TradingJournalRow.owner_id == owner_id)
    if account_id:
        query = query.where(TradingJournalRow.account_id == account_id)
    return list(
        (
            await session.scalars(query.order_by(TradingJournalRow.updated_at.desc()).limit(200))
        ).all()
    )


async def persist_result(
    session: AsyncSession, operation_id: str, status: str, result: dict[str, Any]
) -> None:
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is None:
        raise LonoraError("operation_not_found", 404)
    row.status = status
    row.result = result
    row.updated_at = utcnow()
