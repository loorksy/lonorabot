from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import AgentCreate, AgentUpdate
from lonora_core.user_error import LonoraError
from lonora_db.agent_super_bot import active_super_bot_agents
from lonora_db.agents import agent_data, create_agent, list_agents, update_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.skill_controls import delete_skill_controls
from lonora_db.threads import conversation_thread, thread_data
from lonora_db.transactions import owned_agent

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents")


@router.get("")
async def agents(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        rows = await list_agents(session, owner.id)
        active = await active_super_bot_agents(session, owner.id)
        return [agent_data(row, super_bot_active=row.id in active) for row in rows]


@router.post("", status_code=201)
async def create(
    request: Request, body: AgentCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    if not body.trading_account_id or not body.trading_symbol:
        raise LonoraError("agent_trading_binding_required", 422)
    rt = runtime(request)
    async with rt.db.sessions() as session:
        connection = await BrokerSessionRepository().get(session, owner.id, body.trading_account_id)
        version = connection.version
        if not BrokerConnection.model_validate(connection.payload).enabled:
            raise LonoraError("broker_disabled", 409)
    broker = await rt.services(owner.id).brokers.get(owner.id, body.trading_account_id)
    symbols = await broker.symbols()
    if body.trading_symbol not in symbols:
        raise LonoraError("symbol_not_found", 404)
    specification = await broker.instrument(body.trading_symbol)
    if specification.symbol != body.trading_symbol:
        raise LonoraError("broker_symbol_mismatch", 409)
    async with rt.db.sessions() as session, session.begin():
        connection = await BrokerSessionRepository().get(
            session, owner.id, body.trading_account_id, lock=True
        )
        if connection.version != version:
            raise LonoraError("broker_connection_changed", 409)
        return agent_data(await create_agent(session, owner.id, body))


@router.get("/{agent_id}")
async def read(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        row = await owned_agent(session, owner.id, agent_id)
        active = await active_super_bot_agents(session, owner.id)
        return agent_data(row, super_bot_active=agent_id in active)


@router.post("/{agent_id}/conversation")
async def conversation(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return thread_data(await conversation_thread(session, owner.id, agent_id))


@router.patch("/{agent_id}")
async def configure(
    request: Request,
    agent_id: str,
    body: AgentUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        row = await update_agent(session, owner.id, agent_id, body)
        active = await active_super_bot_agents(session, owner.id)
        return agent_data(row, super_bot_active=agent_id in active)


@router.delete("/{agent_id}")
async def delete(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        agent = await owned_agent(session, owner.id, agent_id, lock=True)
        if agent.role == "personal":
            raise LonoraError("personal_agent_cannot_delete", 409)
        await delete_skill_controls(session, owner.id, agent_id)
        await session.delete(agent)
    return {"deleted": True}
