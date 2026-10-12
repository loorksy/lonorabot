from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import Contract
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.trading_journal import journal_entries
from lonora_db.transactions import resource_data
from lonora_trading.accounts import account_snapshot
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
    if body.api_key:
        config.secret_id = await rt.services(owner.id).secrets.write(
            body.account_id, body.api_key, "broker"
        )
    async with rt.db.sessions() as session, session.begin():
        return resource_data(
            await BrokerSessionRepository().create(
                session, owner.id, config.model_dump(mode="json")
            )
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
        await runtime(request).services(owner.id).brokers.get(owner.id, connection_id)
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
