from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.domain import AgentCreate, AgentUpdate
from lonora_core.user_error import LonoraError
from lonora_db.agent_super_bot import active_super_bot_agents
from lonora_db.agents import agent_data, create_agent, list_agents, update_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.events import emit
from lonora_db.skill_controls import delete_skill_controls
from lonora_db.super_bot import authority_lock
from lonora_db.threads import conversation_thread, thread_data
from lonora_db.transactions import owned_agent
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime
from ..runtime import ApiRuntime

router = APIRouter(prefix="/agents")


async def validate_market(rt: ApiRuntime, owner_id: str, account_id: str, symbol: str) -> int:
    async with rt.db.sessions() as session:
        connection = await BrokerSessionRepository().get(session, owner_id, account_id)
        version = connection.version
        if not BrokerConnection.model_validate(connection.payload).enabled:
            raise LonoraError("broker_disabled", 409)
    broker = await rt.services(owner_id).brokers.get(owner_id, account_id)
    if symbol not in await broker.symbols():
        raise LonoraError("symbol_not_found", 404)
    if (await broker.instrument(symbol)).symbol != symbol:
        raise LonoraError("broker_symbol_mismatch", 409)
    return version


async def recheck_market(
    session: AsyncSession, owner_id: str, account_id: str, version: int
) -> None:
    connection = await BrokerSessionRepository().get(session, owner_id, account_id, lock=True)
    if connection.version != version:
        raise LonoraError("broker_connection_changed", 409)


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
        if body.scope_mode == "flexible":
            async with runtime(request).db.sessions() as session, session.begin():
                return agent_data(await create_agent(session, owner.id, body))
        raise LonoraError("agent_trading_binding_required", 422)
    rt = runtime(request)
    version = await validate_market(rt, owner.id, body.trading_account_id, body.trading_symbol)
    async with rt.db.sessions() as session, session.begin():
        await recheck_market(session, owner.id, body.trading_account_id, version)
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
    rt = runtime(request)
    async with rt.db.sessions() as session:
        await owned_agent(session, owner.id, agent_id)
    version = None
    if "scope_mode" in body.model_fields_set and body.trading_account_id and body.trading_symbol:
        version = await validate_market(rt, owner.id, body.trading_account_id, body.trading_symbol)
    async with rt.db.sessions() as session, session.begin():
        await authority_lock(session, agent_id)
        if version is not None and body.trading_account_id:
            await recheck_market(session, owner.id, body.trading_account_id, version)
        row = await update_agent(session, owner.id, agent_id, body)
        active = await active_super_bot_agents(session, owner.id)
        data = agent_data(row, super_bot_active=agent_id in active)
        emit(session, owner.id, "agent.updated", agent_id=agent_id, payload=data)
        return data


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
