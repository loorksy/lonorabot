from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeResult
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import TradingJournalRow


async def reserve_operation(
    session: AsyncSession,
    owner_id: str,
    operation_id: str,
    account_id: str,
    request_hash: str,
    request: dict[str, Any],
    execution_mode: str = "live",
) -> tuple[TradingJournalRow, bool]:
    # INSERT arbitrates even when no row exists yet; locking a missing row does not.
    created = await session.scalar(
        insert(TradingJournalRow)
        .values(
            operation_id=operation_id,
            owner_id=owner_id,
            account_id=account_id,
            request_hash=request_hash,
            request=request,
            execution_mode=execution_mode,
        )
        .on_conflict_do_nothing(index_elements=[TradingJournalRow.operation_id])
        .returning(TradingJournalRow.operation_id)
    )
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is None:
        raise LonoraError("operation_not_found", 404)
    if (
        row.owner_id != owner_id
        or row.request_hash != request_hash
        or row.execution_mode != execution_mode
    ):
        raise LonoraError("operation_id_conflict", 409)
    return row, created is not None


async def journal_entries(
    session: AsyncSession,
    owner_id: str,
    account_id: str | None = None,
    execution_mode: str = "live",
) -> list[TradingJournalRow]:
    query = select(TradingJournalRow).where(
        TradingJournalRow.owner_id == owner_id, TradingJournalRow.execution_mode == execution_mode
    )
    if account_id:
        query = query.where(TradingJournalRow.account_id == account_id)
    return list(
        (
            await session.scalars(query.order_by(TradingJournalRow.updated_at.desc()).limit(200))
        ).all()
    )


async def persist_result(
    session: AsyncSession, operation_id: str, status: str, result: dict[str, Any]
) -> bool:
    validated = TradeResult.model_validate(result)
    if validated.operation_id != operation_id or validated.status != status:
        raise LonoraError("broker_result_mismatch", 502)
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is None:
        raise LonoraError("operation_not_found", 404)
    # An observer or late execution response may arrive after reconciliation. Never
    # regress a durable terminal receipt to uncertainty or replace its evidence.
    if row.status in {"confirmed", "failed"}:
        return False
    origin = row.result.get("details", {}).get("execution")
    if isinstance(origin, dict):
        # Attribution comes from the owned session and fenced run, not broker payload.
        validated.details = {**validated.details, "execution": origin}
    else:
        validated.details = {
            key: value for key, value in validated.details.items() if key != "execution"
        }
    # Pre-send observations are server-owned historical facts. A later broker
    # reconciliation receipt must not erase or replace them with today's market.
    quality = row.result.get("details", {}).get("execution_quality")
    if isinstance(quality, dict):
        validated.details = {**validated.details, "execution_quality": quality}
    evidence = row.result.get("details", {}).get("execution_evidence")
    if isinstance(evidence, dict):
        validated.details = {**validated.details, "execution_evidence": evidence}
    else:
        # An adapter response cannot invent server-captured historical evidence.
        validated.details.pop("execution_evidence", None)
    row.status = status
    row.result = validated.model_dump(mode="json")
    row.updated_at = utcnow()
    return True


async def mark_reconciliation_attempt(session: AsyncSession, operation_id: str) -> None:
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is not None and row.status in {"ambiguous", "submitted"}:
        # Rotate unresolved/unavailable accounts through the bounded observer batch;
        # do not replace their original request, execution receipt, or status.
        row.updated_at = utcnow()
