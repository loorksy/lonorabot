from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.trading import (
    TERMINAL_STATUSES,
    OperationResolution,
    TradeRequest,
    TradeResult,
)
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.trading_journal import journal_entries
from lonora_db.transactions import resource_data
from lonora_trading.accounts import account_snapshot
from lonora_trading.connections import connect_account
from lonora_trading.journal import journal_data
from lonora_trading.owner_controls import attest_operation
from lonora_trading.simulation import import_simulation

from ..middleware.auth import require_owner, runtime


class SimulationInput(Contract):
    snapshot: dict[str, Any]


router = APIRouter(prefix="/trading")


@router.get("/connections")
async def connections(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [
            resource_data(row) for row in await BrokerSessionRepository().list(session, owner.id)
        ]


@router.post("/connections", status_code=201)
async def connect(
    request: Request, body: BrokerConnection, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    return await connect_account(runtime(request).db, owner.id, body)


@router.delete("/connections/{connection_id}")
async def disconnect(
    request: Request, connection_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    from lonora_trading.broker_manage import disconnect as disconnect_connection

    rt = runtime(request)
    services = rt.services(owner.id)
    # The same disconnect as from chat (9.3, Q8): refused while an operation on this
    # account is uncertain; prepare_delete first; a MetaApi account Lonora created is
    # removed there too; the password is deleted, the token kept. The journal outlives it.
    await disconnect_connection(rt.db, services.brokers, owner.id, connection_id)
    return {"deleted": True}


@router.get("/accounts/{connection_id}")
async def account(
    request: Request, connection_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    return await account_snapshot(
        await runtime(request).services(owner.id).brokers.get(owner.id, connection_id),
        await runtime(request).services(owner.id).brokers.account(owner.id, connection_id),
    )


@router.post("/connections/{connection_id}/simulation")
async def simulation(
    request: Request,
    connection_id: str,
    body: SimulationInput,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    return await import_simulation(runtime(request).db, owner.id, connection_id, body.snapshot)


@router.post("/execute")
async def execute(
    request: Request, body: TradeRequest, owner: OwnerIdentity = Depends(require_owner)
) -> TradeResult:
    return await runtime(request).services(owner.id).trading.execute(owner.id, body)


@router.get("/journal")
async def journal(
    request: Request,
    account_id: str | None = None,
    thread_id: str | None = None,
    owner: OwnerIdentity = Depends(require_owner),
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [
            journal_data(row)
            for row in await journal_entries(session, owner.id, account_id, thread_id=thread_id)
        ]


@router.post("/journal/{operation_id}/resolve")
async def resolve(
    request: Request,
    operation_id: str,
    body: OperationResolution,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """Owner attestation for an uncertain operation; it clears the block, never resends.

    The authenticated owner session (cookie with CSRF, or bearer token) is the actor. The
    original receipt and evidence stay on the row and the attestation is a durable event.
    """
    async with runtime(request).db.sessions() as session, session.begin():
        row = await attest_operation(
            session,
            owner.id,
            operation_id,
            body,
            {
                "kind": "owner",
                "owner_id": owner.id,
                "authentication": "owner_session",
                "session_ref": owner.token_hash[:16],
            },
        )
        return journal_data(row)


class ApprovalDecision(Contract):
    decision: Literal["approve", "reject"]


@router.get("/approvals")
async def approvals(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    from lonora_db.schema import TradeApprovalRow, TradingJournalRow
    from lonora_db.trade_approvals import approval_data, settle_if_expired
    from lonora_db.transactions import owned_thread
    from sqlalchemy import select

    db = runtime(request).db
    async with db.sessions() as session, session.begin():
        # Lazily settled: a pending card past its expiry becomes expired (with its event).
        await owned_thread(session, owner.id, thread_id)
        overdue = await session.scalars(
            select(TradeApprovalRow.id).where(
                TradeApprovalRow.owner_id == owner.id,
                TradeApprovalRow.thread_id == thread_id,
                TradeApprovalRow.status == "pending",
                TradeApprovalRow.expires_at <= utcnow(),
            )
        )
        for identifier in list(overdue):
            await settle_if_expired(session, owner.id, identifier)
    async with db.sessions() as session:
        await owned_thread(session, owner.id, thread_id)
        rows = await session.scalars(
            select(TradeApprovalRow)
            .where(TradeApprovalRow.owner_id == owner.id, TradeApprovalRow.thread_id == thread_id)
            .order_by(TradeApprovalRow.created_at.desc())
            .limit(200)
        )
        cards: list[dict[str, Any]] = []
        for row in reversed(list(rows)):
            card = approval_data(row)
            # Journal reconciliation remains authoritative after the worker has
            # completed its tool turn. A fresh browser never displays an old
            # ambiguous receipt as if reconciliation had not happened.
            if row.status in {"approved", "completed"}:
                resolved: list[dict[str, Any]] = []
                receipts = {result["operation_id"]: result for result in row.results}
                for proposal in row.requests:
                    result = receipts.get(proposal["operation_id"])
                    journal = await session.get(TradingJournalRow, proposal["operation_id"])
                    if result is None:
                        if journal and journal.owner_id == owner.id and journal.result:
                            resolved.append(journal.result)
                        continue
                    resolved.append(
                        journal.result
                        if journal
                        and journal.owner_id == owner.id
                        and journal.status in TERMINAL_STATUSES
                        else result
                    )
                card["results"] = resolved
            cards.append(card)
        return cards


@router.post("/approvals/{approval_id}/decision")
async def approval_decision(
    request: Request,
    approval_id: str,
    body: ApprovalDecision,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    from lonora_db.trade_approvals import decide, settle_if_expired

    db = runtime(request).db
    async with db.sessions() as session, session.begin():
        # Settled (and committed) first, so the refusal below leaves the card expired.
        expired = await settle_if_expired(session, owner.id, approval_id)
    if expired:
        raise LonoraError("trade_approval_expired", 409)
    async with db.sessions() as session, session.begin():
        return await decide(session, owner.id, approval_id, body.decision)


@router.post("/approvals/{approval_id}/renew")
async def approval_renew(
    request: Request, approval_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    """«طلب جديد» on an expired approval: the agent is asked again in the same
    conversation (a run with a fixed server note). It creates no approval itself: the
    agent re-validates and raises a new card through the normal path."""
    from lonora_db.runs import run_data
    from lonora_db.trade_approvals import renew_approval

    async with runtime(request).db.sessions() as session, session.begin():
        return run_data(await renew_approval(session, owner.id, approval_id))
