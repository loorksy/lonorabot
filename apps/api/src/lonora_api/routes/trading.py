from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import Contract
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.trading_journal import journal_entries
from lonora_db.transactions import resource_data
from lonora_trading.accounts import account_snapshot
from lonora_trading.connections import connect_account
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.journal import journal_data
from lonora_trading.simulation import import_simulation

from ..middleware.auth import require_owner, runtime


class ConnectionCreate(BrokerConnection):
    api_key: str | None = None


class SimulationInput(Contract):
    snapshot: dict[str, Any]


router = APIRouter(prefix="/trading")


@router.get("/controls")
async def controls(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> TradingControl:
    return await read_controls(runtime(request).db)


@router.put("/controls")
async def set_controls(
    request: Request, body: TradingControl, owner: OwnerIdentity = Depends(require_owner)
) -> TradingControl:
    return await save_controls(runtime(request).db, body)


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
    request: Request, body: ConnectionCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    config = BrokerConnection.model_validate(body.model_dump(exclude={"api_key"}))
    return await connect_account(
        rt.db,
        EncryptedSecretStore(rt.db, rt.settings.encryption_key.get_secret_value(), owner.id),
        owner.id,
        config,
        body.api_key,
    )


@router.delete("/connections/{connection_id}")
async def disconnect(
    request: Request, connection_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        await BrokerSessionRepository().delete(session, owner.id, connection_id)
    prior = rt.services(owner.id).brokers.connections.pop(connection_id, None)
    if prior:
        await prior[1].close()
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
    request: Request, account_id: str | None = None, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [journal_data(row) for row in await journal_entries(session, owner.id, account_id)]


class ApprovalDecision(Contract):
    decision: Literal["approve", "reject"]


@router.get("/approvals")
async def approvals(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    from lonora_db.schema import TradeApprovalRow, TradingJournalRow
    from lonora_db.trade_approvals import approval_data
    from lonora_db.transactions import owned_thread
    from sqlalchemy import select

    async with runtime(request).db.sessions() as session:
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
                        and journal.status in {"confirmed", "failed"}
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
    from lonora_db.trade_approvals import decide

    async with runtime(request).db.sessions() as session, session.begin():
        return await decide(session, owner.id, approval_id, body.decision)
