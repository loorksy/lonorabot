from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.trading import (
    IN_PROGRESS_STATUSES,
    TERMINAL_STATUSES,
    OperationResolution,
    TradeResult,
)
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import RunRow, ThreadRow, TradingJournalRow

# Facts the execution boundary recorded itself: never replaced by a broker receipt.
# execution_evidence: planned/before-send snapshots; risk_assessment: the monetary limit
# evaluation older rows recorded; admission_block: the boundary decision that stopped it.
SERVER_EVIDENCE = ("execution_evidence", "risk_assessment", "admission_block")


async def reserve_operation(
    session: AsyncSession,
    owner_id: str,
    operation_id: str,
    account_id: str,
    request_hash: str,
    request: dict[str, Any],
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
        )
        .on_conflict_do_nothing(index_elements=[TradingJournalRow.operation_id])
        .returning(TradingJournalRow.operation_id)
    )
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is None:
        raise LonoraError("operation_not_found", 404)
    if row.owner_id != owner_id or row.request_hash != request_hash:
        raise LonoraError("operation_id_conflict", 409)
    return row, created is not None


async def anchor_operation(session: AsyncSession, row: TradingJournalRow, run: RunRow) -> None:
    """Place a fresh operation in the conversation of the Run that requested it.

    Presentation metadata only, written once beside the reservation: the visible thread
    (a subagent's origin conversation, else the Run's own) and its next message seq, as
    ``ln_trade_approvals.timeline_seq``. Nothing in execution or authority reads it.
    """
    if row.thread_id is not None:
        return
    origin = run.model_metadata.get("origin_thread_id")
    thread = await session.get(
        ThreadRow, origin if isinstance(origin, str) and origin else run.thread_id
    )
    if thread is None or thread.owner_id != row.owner_id:
        return
    row.thread_id, row.timeline_seq = thread.id, thread.next_seq


async def journal_entries(
    session: AsyncSession,
    owner_id: str,
    account_id: str | None = None,
    thread_id: str | None = None,
) -> list[TradingJournalRow]:
    query = select(TradingJournalRow).where(TradingJournalRow.owner_id == owner_id)
    if account_id:
        query = query.where(TradingJournalRow.account_id == account_id)
    if thread_id:
        query = query.where(TradingJournalRow.thread_id == thread_id)
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
    # regress a durable terminal receipt (including an owner attestation) to
    # uncertainty or replace its evidence.
    if row.status in TERMINAL_STATUSES:
        return False
    if status in IN_PROGRESS_STATUSES:
        # Only the executor's own send boundary moves reserved -> submitted.
        raise LonoraError("operation_status_transition_invalid", 409)
    previous = {"status": row.status, "code": row.result.get("code")}
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
    for key in SERVER_EVIDENCE:
        evidence = row.result.get("details", {}).get(key)
        if isinstance(evidence, dict):
            validated.details = {**validated.details, key: evidence}
        else:
            # An adapter response cannot invent server-captured historical evidence.
            validated.details.pop(key, None)
    if status == "resolved":
        # Settling uncertainty without the outcome keeps what was known before it.
        validated.details = {**validated.details, "prior_receipt": previous}
    row.status = status
    row.result = validated.model_dump(mode="json")
    row.updated_at = utcnow()
    return True


async def release_reservation(
    session: AsyncSession, operation_id: str, reason: str
) -> TradingJournalRow | None:
    """Prove an abandoned reservation unsent: atomic with the executor's send boundary.

    The executor moves ``reserved`` to ``submitted`` only under this same row lock, so a
    released reservation can never be sent afterwards; its late sender stops before the
    broker. A row that already crossed the boundary is never released here.
    """
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is None or row.status != "reserved":
        return None
    await persist_result(
        session,
        operation_id,
        "failed",
        TradeResult(
            operation_id=operation_id,
            status="failed",
            code="operation_not_sent",
            details={"send_state": "not_sent", "release_reason": reason},
        ).model_dump(mode="json"),
    )
    return row


async def resolve_operation(
    session: AsyncSession,
    owner_id: str,
    operation_id: str,
    resolution: OperationResolution,
    actor: dict[str, Any],
) -> TradingJournalRow:
    """Record an audited owner attestation for an outcome broker evidence cannot establish.

    Only an ``ambiguous`` live operation qualifies: an in-progress one may still receive
    its real broker response, and a settled one already has a known outcome. Nothing is
    deleted; the uncertain receipt, its evidence and the attestation stay on the row.
    """
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("operation_not_found", 404)
    if row.status in IN_PROGRESS_STATUSES:
        raise LonoraError("operation_in_progress", 409)
    if row.status != "ambiguous":
        raise LonoraError("operation_already_settled", 409)
    now = utcnow()
    details = row.result.get("details", {})
    row.status = "resolved"
    row.result = {
        **row.result,
        "status": "resolved",
        "code": "owner_attested_" + resolution.outcome,
        "details": {
            **details,
            "prior_receipt": {"status": "ambiguous", "code": row.result.get("code")},
            "resolution": {
                "source": "owner",
                "outcome": resolution.outcome,
                "statement": resolution.statement,
                "broker_reference": resolution.broker_reference,
                "actor": actor,
                "resolved_at": now.isoformat(),
                "broker_confirmed": False,
            },
        },
    }
    row.updated_at = now
    return row


async def mark_reconciliation_attempt(session: AsyncSession, operation_id: str) -> None:
    row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
    if row is not None and row.status in {"ambiguous", "submitted", "reserved"}:
        # Rotate unresolved/unavailable accounts through the bounded observer batch;
        # do not replace their original request, execution receipt, or status.
        row.updated_at = utcnow()
